"""Security model (SPEC §17, acceptance A12-A14): the desk's own controls.

Switch addressing (`owner_and_owner_agents`) refuses strangers before the desk sees a message;
these tests prove the desk is also safe on its own: owner-only verbs, approvals that agents and
look-alikes cannot resolve, allowlists, no shell, TTL, rate limit, freeze, destructive git.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from roomservice import store
from roomservice.agents.base import owner_ids
from roomservice.agents.desk import DeskAgent, add_owner, new_pairing_code
from roomservice.bus import Bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Settings, load_desk_config
from roomservice.contracts.switch import DomainEvent, MessagePayload
from roomservice.desk.allowlist import url_allowed
from roomservice.desk.approvals import Approvals
from roomservice.desk.os.dry import DryAdapter

OWNER = "@owner:srv"
HQ = RoomInfo(id="r1", name="roomservice-hq", kind=RoomKind.HQ, conn_id="c1")
MISSION = RoomInfo(id="r2", name="mission-volt", kind=RoomKind.MISSION, conn_id="c2")
ROOT = Path(__file__).resolve().parents[2] / "roomservice"


class FakeHttp:
    def __init__(self):
        self.posts: list[str] = []
        self.participants: list[dict] = []

    async def op(self, name, args, conn_id=None):
        if name == "post_message":
            self.posts.append(args["body"])
        if name == "list_participants":
            return {"participants": self.participants}
        return {}

    async def post(self, room_id, content):
        self.posts.append(content)
        return "e"

    async def upload(self, *a, **k):
        return {}

    async def typing(self, room_id, on):
        pass

    async def health(self):
        return True


@pytest.fixture
async def desk(fixtures_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SWITCH_URL", "http://localhost:1")
    store.save_agent_creds("http://localhost:1", "desk-laptop", "id1", "k1")
    add_owner(OWNER, "owner", "roomservice-hq")
    http = FakeHttp()
    agent = DeskAgent(
        cfg=load_desk_config(fixtures_dir / "desk_example.yaml"),
        settings=Settings(),
        adapter=DryAdapter(delay_s=0.01),
        http=http,
        bus=Bus(),
    )
    agent.test_http = http  # type: ignore[attr-defined]
    agent._tasks = [asyncio.create_task(agent._worker())]
    yield agent
    for t in agent._tasks:
        t.cancel()


_n = 0


async def say(agent, body, sender=OWNER, name="owner", room=HQ, addressed=True):
    global _n
    _n += 1
    msg = MessagePayload(
        addressed=addressed,
        sender=sender,
        sender_name=name,
        message_id=f"s{_n}",
        body=body,
        timestamp=1,
    )
    ev = DomainEvent(type="message", room_id=room.id, payload={}, sequence=_n)
    await agent.on_message(room, ev, msg)


def posts(agent) -> list[str]:
    return agent.test_http.posts


def ops(agent, name):
    return [c for c in agent.adapter.calls if c[0] == name]


def git_adds(agent):
    return [c for c in ops(agent, "run") if c[1][0][:2] == ("git", "add")]


def code_of(agent) -> str:
    ask = next(x for x in reversed(posts(agent)) if x.startswith("⚠️ approval needed"))
    m = re.search(r"ok ([A-Z0-9]{4})", ask)
    assert m
    return m.group(1)


async def pending_commit(desk) -> str:
    await say(desk, "@hands boot volt")
    await desk.drain()
    await say(desk, '@hands commit "ship it"')
    await desk.drain()
    return code_of(desk)


# -- A12: someone else commands the desk ---------------------------------------------------


async def test_a12_stranger_close_all_does_nothing(desk):
    await say(desk, "@hands open browser")
    await desk.drain()
    await say(desk, "@hands close all", sender="@stranger:srv", name="stranger")
    await desk.drain()
    # `close all` always needs an owner approval; nothing is quit until an owner says ok
    assert ops(desk, "quit_app") == []
    code = code_of(desk)
    await say(desk, f"ok {code}", sender="@stranger:srv", name="stranger")
    await desk.drain()
    assert ops(desk, "quit_app") == []
    assert desk.approvals.get(code) is not None  # still open, nobody resolved it


@pytest.mark.parametrize("verb", ["freeze", "unfreeze", "ok K7Q3", "no K7Q3"])
async def test_owner_only_verbs_refuse_strangers(desk, verb):
    await say(desk, f"@hands {verb}", sender="@stranger:srv", name="stranger")
    assert posts(desk)[-1].startswith("⛔ refused · ")
    assert posts(desk)[-1].endswith("— owner only")
    assert not desk.frozen


async def test_display_name_spoofing_does_not_make_an_owner(desk):
    """Identity is the exact participant id: a stranger *named* owner is still a stranger."""
    await say(desk, "@hands freeze", sender="@mallory:srv", name="owner")
    assert not desk.frozen
    code = await pending_commit(desk)
    await say(desk, f"ok {code}", sender="@mallory:srv", name="owner")
    await desk.drain()
    assert desk.approvals.get(code) is not None
    assert git_adds(desk) == []


async def test_id_lookalikes_are_not_owners(desk):
    for fake in ("@owner:srv2", "@OWNER:srv", "@owner:srv ", "owner"):
        await say(desk, "@hands freeze", sender=fake, name="owner")
        assert not desk.frozen


# -- agents can never pair / approve / freeze -------------------------------------------------


async def test_agent_cannot_approve_even_if_listed_as_owner(desk):
    code = await pending_commit(desk)
    # worst case: an agent id ended up in owners.json; the identity heuristics still block it
    add_owner("@builder:srv", "Builder", "roomservice-hq")
    await say(desk, f"ok {code}", sender="@builder:srv", name="Builder")
    await desk.drain()
    assert desk.approvals.get(code) is not None
    assert git_adds(desk) == []


async def test_agent_detected_by_participant_type_cannot_approve(desk):
    code = await pending_commit(desk)
    add_owner("@bot:srv", "Helpful", "roomservice-hq")
    desk.test_http.participants = [{"id": "@bot:srv", "name": "Helpful", "type": "agent"}]
    await say(desk, f"yes {code}", sender="@bot:srv", name="Helpful")
    await desk.drain()
    assert desk.approvals.get(code) is not None
    assert git_adds(desk) == []


async def test_agent_cannot_pair(desk):
    new_pairing_code()
    code = store.read_json(store.home() / "pairing.json")["code"]
    await say(desk, f"@hands pair {code}", sender="@concierge:srv", name="Concierge")
    assert posts(desk)[-1] == "⛔ refused · pair — agents cannot pair"
    desk.test_http.participants = [{"id": "@x:srv", "name": "Mx", "participant_type": "agent"}]
    await say(desk, f"@hands pair {code}", sender="@x:srv", name="Mx")
    assert posts(desk)[-1] == "⛔ refused · pair — agents cannot pair"
    assert owner_ids() == {OWNER}


async def test_agent_cannot_freeze(desk):
    await say(desk, "@hands freeze", sender="@builder:srv", name="Builder")
    assert not desk.frozen


async def test_pair_needs_hq_and_a_valid_code(desk):
    new_pairing_code()
    code = store.read_json(store.home() / "pairing.json")["code"]
    await say(desk, f"@hands pair {code}", sender="@new:srv", name="new", room=MISSION)
    assert "pair from an HQ room" in posts(desk)[-1]
    await say(desk, "@hands pair 000000x", sender="@new:srv", name="new")
    assert "bad or expired pairing code" in posts(desk)[-1]
    assert "@new:srv" not in owner_ids()


async def test_five_bad_pair_codes_burn_the_code(desk):
    new_pairing_code()
    real = store.read_json(store.home() / "pairing.json")["code"]
    bad = "111111" if real != "111111" else "222222"
    for _ in range(5):
        await say(desk, f"@hands pair {bad}", sender="@new:srv", name="new")
    await say(desk, f"@hands pair {real}", sender="@new:srv", name="new")
    assert "@new:srv" not in owner_ids()


def test_only_guarded_paths_touch_pairing_and_approvals():
    src = (ROOT / "agents" / "desk.py").read_text()
    for fn in ("_resolve", "_pair"):
        body = src.split(f"async def {fn}(")[1].split("\n    async def ")[0]
        assert "_is_agent" in body, fn


# -- A13: allowlist ----------------------------------------------------------------------


async def test_a13_open_steam_is_refused_with_exact_text(desk):
    await say(desk, "@hands open Steam")
    await desk.drain()
    assert posts(desk)[-1] == "⛔ refused · open Steam — not on the allowlist"
    assert ops(desk, "open_app") == []


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://example.com",
        "data:text/html,<script>1</script>",
        "ftp://example.com/x",
        "https://user:pw@example.com",
        "https://exa mple.com",
        "http://localhost.evil.com",
        "http://127.0.0.1.evil.com",
        "http://localhost@evil.com",
        "",
    ],
)
def test_url_rules_deny(url):
    assert not url_allowed(url)


@pytest.mark.parametrize(
    "url", ["https://github.com", "http://localhost:5173", "http://127.0.0.1:8080/x?a=1&b=2"]
)
def test_url_rules_allow(url):
    assert url_allowed(url)


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "javascript:alert(1)", "http://example.com", "calendar;rm"]
)
async def test_url_verb_refuses_bad_urls(desk, url):
    await say(desk, f'@hands url "{url}"')
    await desk.drain()
    assert posts(desk)[-1].startswith("⛔ refused · ")
    assert ops(desk, "open_url") == []


async def test_unknown_script_and_close_are_refused(desk):
    await say(desk, "@hands run rm-rf")
    await say(desk, "@hands close Steam")
    await desk.drain()
    refusals = [p for p in posts(desk) if p.startswith("⛔")]
    assert refusals == [
        "⛔ refused · run rm-rf — not on the allowlist",
        "⛔ refused · close Steam — not on the allowlist",
    ]
    assert ops(desk, "run") == [] and ops(desk, "quit_app") == []


# -- A14: freeze (chat and HUD `S` path) ------------------------------------------------------


async def test_a14_hud_freeze_banner_then_commands_refused_until_unfreeze(desk):
    events = []

    async def collect():
        async for ev in desk.bus.subscribe():
            events.append(ev)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)
    desk.bus.on_freeze = desk._hud_freeze  # what DeskAgent.start() wires
    await desk.bus.on_freeze(True)
    await asyncio.sleep(0.01)
    assert any(e.type == "freeze" and e.on for e in events)  # HUD banner event
    assert desk.frozen
    await say(desk, "@hands open browser")
    await say(desk, "@hands url github")
    assert posts(desk)[-2:] == ["⛔ refused · paused by owner"] * 2
    await say(desk, "@hands status")
    await say(desk, "@hands help")
    await desk.drain()
    assert any(p.startswith("✅ status") and "Paused: yes" in p for p in posts(desk))
    assert any("boot <project>" in p for p in posts(desk))
    assert ops(desk, "open_app") == [] and ops(desk, "open_url") == []
    await desk.bus.on_freeze(False)
    await asyncio.sleep(0.01)
    assert any(e.type == "freeze" and not e.on for e in events)
    await say(desk, "@hands open browser")
    await desk.drain()
    assert ops(desk, "open_app")
    task.cancel()


async def test_frozen_desk_does_not_run_an_approved_commit(desk):
    code = await pending_commit(desk)
    await desk.set_frozen(True, "owner")
    await say(desk, f"ok {code}")
    await desk.drain()
    assert git_adds(desk) == []
    assert posts(desk)[-1] == "⛔ refused · paused by owner"


# -- no shell ------------------------------------------------------------------------------


def test_no_shell_anywhere_in_runtime():
    bad = re.compile(r"shell\s*=\s*True|create_subprocess_shell|os\.system\(|os\.popen\(")
    hits = [
        f"{p.relative_to(ROOT)}:{i}: {line.strip()}"
        for p in ROOT.rglob("*.py")
        for i, line in enumerate(p.read_text().splitlines(), 1)
        if bad.search(line)
    ]
    assert hits == [], hits


def test_open_terminal_is_the_only_place_a_command_string_is_composed():
    """open_terminal gets desk.yaml's own `cmd`; chat text never reaches it."""
    src = (ROOT / "desk" / "actions.py").read_text()
    uses = re.findall(r"open_terminal\(([^)]*)\)", src)
    assert len(uses) == 1 and "t.cmd" in uses[0]  # t comes from the project profile in desk.yaml


async def test_shell_metacharacters_in_chat_never_reach_a_process(desk):
    await say(desk, '@hands say "$(rm -rf ~); `reboot` && x"')
    await say(desk, "@hands open browser; rm -rf /")
    await desk.drain()
    assert ops(desk, "run") == []
    assert ops(desk, "open_app") == []  # "browser;" is not an app key


# -- destructive git -----------------------------------------------------------------------


async def test_commit_and_push_need_approval_and_never_force(desk):
    await say(desk, "@hands boot volt")
    await desk.drain()
    await say(desk, '@hands commit "--force; git reset --hard && rm -rf ."')
    await say(desk, "@hands push")
    await say(desk, "@hands push --force")
    await desk.drain()
    assert ops(desk, "run") == []  # nothing ran before approval
    assert any("push takes no arguments (never forced)" in p for p in posts(desk))
    for ap in list(desk.approvals.open_approvals()):
        await say(desk, f"ok {ap.code}")
        await desk.drain()
    argvs = [c[1][0] for c in ops(desk, "run")]
    assert argvs == [
        ("git", "add", "-A"),
        ("git", "commit", "-m", "--force; git reset --hard && rm -rf ."),
        ("git", "push"),
    ]
    assert not {a for argv in argvs for a in argv[:3]} & {
        "--force",
        "-f",
        "--force-with-lease",
        "reset",
        "rm",
        "clean",
    }


async def test_declined_commit_never_runs(desk):
    code = await pending_commit(desk)
    await say(desk, f"no {code}")
    await desk.drain()
    assert ops(desk, "run") == []
    assert any(p.startswith("🚫 declined by owner") for p in posts(desk))


# -- approval TTL --------------------------------------------------------------------------


def test_approval_expires_after_ttl_and_cannot_be_resolved():
    now = [1000.0]
    closed = []
    ap = Approvals(ttl_s=300, publish=lambda e: None, clock=lambda: now[0])
    ap.on_close = lambda a, r: closed.append(r)
    a = ap.create('commit "x"', "r1")
    now[0] += 299
    assert ap.sweep() == []
    now[0] += 2
    assert [x.code for x in ap.sweep()] == [a.code]
    assert closed == ["expired"]
    r = ap.resolve(f"ok {a.code}", OWNER, "owner", {OWNER})
    assert r is not None and r.result == "unknown"


def test_approval_resolved_at_the_ttl_boundary_is_expired():
    now = [0.0]
    ap = Approvals(ttl_s=300, publish=lambda e: None, clock=lambda: now[0])
    a = ap.create("push", "r1")
    now[0] = 300.0
    r = ap.resolve(f"ok {a.code}", OWNER, "owner", {OWNER})
    assert r is not None and r.result == "expired"


async def test_desk_announces_expiry_and_refuses_late_ok(desk):
    code = await pending_commit(desk)
    ap = desk.approvals.get(code)
    ap.expires_at -= 301  # time travel without sleeping
    desk.approvals.sweep()
    await asyncio.sleep(0.05)
    assert any(p.startswith(f"⌛ expired · {code}") for p in posts(desk))
    await say(desk, f"ok {code}")
    await desk.drain()
    assert posts(desk)[-1] == f"⛔ refused · ok {code} — no open approval {code}"
    assert git_adds(desk) == []


# -- runaway loop --------------------------------------------------------------------------


async def test_default_rate_limit_is_20_per_minute(desk):
    assert desk.cfg.limits.actions_per_minute == 20
    for _ in range(22):
        await say(desk, "@hands status")
    await desk.drain()
    p = posts(desk)
    assert p.count("⛔ refused · rate limit (20/min)") == 2
    assert len([x for x in p if x.startswith("✅ status")]) == 20


async def test_five_commands_per_message(desk):
    await say(desk, "\n".join(["@hands status"] * 7))
    await desk.drain()
    p = posts(desk)
    assert "⛔ refused · more than 5 commands in one message" in p
    assert len([x for x in p if x.startswith("✅ status")]) == 5


async def test_windows_adapter_cannot_be_talked_into_a_shell(monkeypatch):
    from roomservice.desk.os import base
    from roomservice.desk.os.windows import WindowsAdapter

    seen: list[list[str]] = []

    async def fake(argv, timeout_s=30):
        seen.append(list(argv))

    monkeypatch.setattr(base, "exec_ok", fake)
    a = WindowsAdapter()
    await a.open_url("https://x.com/?a=1&calc")
    assert seen[0][0] == "rundll32" and seen[0][-1] == "https://x.com/?a=1&calc"
    await a.speak("x’; calc; ‘y it's", "v", 190)
    script = seen[1][-1]
    assert "x’’; calc; ‘‘y it''s" in script
