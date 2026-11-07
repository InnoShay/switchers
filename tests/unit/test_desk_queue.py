"""DeskAgent queue behaviour (SPEC §12.4, §20.2): serial order, queued receipt, rate limit,
freeze/unfreeze. No Switch, no OS: a recording HTTP stub and the dry adapter."""

import asyncio

import pytest

from roomservice import store
from roomservice.agents.desk import DeskAgent, add_owner
from roomservice.bus import Bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Limits, Settings, load_desk_config
from roomservice.contracts.switch import DomainEvent, MessagePayload
from roomservice.desk.os.dry import DryAdapter

OWNER = "@owner:srv"
HQ = RoomInfo(id="r1", name="roomservice-hq", kind=RoomKind.HQ, conn_id="c1")


class FakeHttp:
    def __init__(self):
        self.posts: list[str] = []
        self.ops: list[tuple[str, dict]] = []

    async def op(self, name, args, conn_id=None):
        self.ops.append((name, args))
        if name == "post_message":
            self.posts.append(args["body"])
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
    cfg = load_desk_config(fixtures_dir / "desk_example.yaml")
    http = FakeHttp()
    agent = DeskAgent(
        cfg=cfg,
        settings=Settings(),
        adapter=DryAdapter(delay_s=0.05),
        http=http,
        bus=Bus(),
    )
    agent.test_http = http  # type: ignore[attr-defined]
    agent._tasks = [asyncio.create_task(agent._worker())]
    yield agent
    for t in agent._tasks:
        t.cancel()


_n = 0


async def say(agent, body, sender=OWNER, name="owner"):
    global _n
    _n += 1
    msg = MessagePayload(
        addressed=True,
        sender=sender,
        sender_name=name,
        message_id=f"m{_n}",
        body=body,
        timestamp=1,
    )
    ev = DomainEvent(type="message", room_id=HQ.id, payload={}, sequence=_n)
    await agent.on_message(HQ, ev, msg)


def posts(agent):
    return agent.test_http.posts


async def test_serial_order_and_queued_receipt(desk):
    await say(desk, "@hands open browser\n@hands say hi\n@hands status")
    await desk.drain()
    p = posts(desk)
    done = [x for x in p if x.startswith("✅")]
    assert [x.split(" ·")[0].split("\n")[0] for x in done] == [
        "✅ open browser",
        "✅ say hi",
        "✅ status",
    ]
    queued = [x for x in p if x.startswith("⏳ queued · ")]
    assert queued and all("(busy with " in x for x in queued)
    # a queued receipt always precedes that command's own result
    assert p.index(queued[0]) < p.index(done[1])


async def test_busy_names_the_current_command(desk):
    await say(desk, "@hands open browser")
    await asyncio.sleep(0.01)  # worker is now inside the 50 ms dry action
    await say(desk, "@hands say hello")
    await desk.drain()
    assert "⏳ queued · say hello (busy with open browser)" in posts(desk)


async def test_rate_limit(desk):
    desk.cfg.limits = Limits(actions_per_minute=3)
    for _ in range(5):
        await say(desk, "@hands status")
    await desk.drain()
    p = posts(desk)
    assert p.count("⛔ refused · rate limit (3/min)") == 2
    assert len([x for x in p if x.startswith("✅ status")]) == 3


async def test_freeze_and_unfreeze(desk):
    await say(desk, "@hands freeze")
    assert desk.frozen
    assert posts(desk)[-1] == "🧊 paused by owner"
    await say(desk, "@hands open browser")
    assert posts(desk)[-1] == "⛔ refused · paused by owner"
    await say(desk, "@hands status")
    await say(desk, "@hands help")
    await desk.drain()
    assert any(x.startswith("✅ status") and "Paused: yes" in x for x in posts(desk))
    assert any(x.startswith("@hands <verb>") or "boot <project>" in x for x in posts(desk))
    await say(desk, "@hands unfreeze")
    assert not desk.frozen
    assert posts(desk)[-1] == "▶ resumed by owner"
    await say(desk, "@hands open browser")
    await desk.drain()
    assert posts(desk)[-1].startswith("✅ open browser")


async def test_freeze_is_owner_only(desk):
    await say(desk, "@hands freeze", sender="@stranger:srv", name="stranger")
    assert not desk.frozen
    assert posts(desk)[-1] == "⛔ refused · freeze — owner only"


async def test_hud_freeze_callback(desk):
    await desk._hud_freeze(True)
    assert desk.frozen
    await desk._hud_freeze(False)
    assert not desk.frozen


async def test_queued_jobs_are_refused_when_frozen_before_they_run(desk):
    await say(desk, "@hands open browser\n@hands say hi")
    await desk.set_frozen(True, "owner")
    await desk.drain()
    assert "⛔ refused · paused by owner" in posts(desk)


async def test_too_many_commands_and_didnt_understand(desk):
    await say(desk, "\n".join(["@hands status"] * 6))
    await say(desk, "@hands dance")
    await desk.drain()
    p = posts(desk)
    assert "⛔ refused · more than 5 commands in one message" in p
    assert '⛔ didn\'t understand · "dance" · try: @computer help' in p


async def test_commit_asks_for_approval_then_owner_ok_runs_it(desk, tmp_path):
    await say(desk, "@hands boot volt")
    await desk.drain()
    await say(desk, '@hands commit "waitlist page v1"')
    await desk.drain()
    ask = next(x for x in posts(desk) if x.startswith("⚠️ approval needed"))
    assert 'commit "waitlist page v1" in volt' in ask
    code = ask.split("ok ")[1].split()[0]
    assert len(code) == 4
    await say(desk, f"ok {code}")  # unaddressed-style plain reply
    await desk.drain()
    assert posts(desk)[-1].startswith("✅ approved by owner")
    assert [c for c in desk.adapter.calls if c[0] == "run"][0][1][0] == ("git", "add", "-A")
