"""RS-07: dynamic project discovery, detection, and the approval-gated `exec` verb."""

import json

import pytest
from freezegun import freeze_time

from roomservice.contracts.config import load_desk_config
from roomservice.desk import discover
from roomservice.desk.discover import Ambiguous, NotFound, Resolved
from tests.unit.test_desk_queue import HQ, desk, posts, say  # noqa: F401


@pytest.fixture
def cfg(fixtures_dir):
    return load_desk_config(fixtures_dir / "desk_example.yaml")


def mk(root, *names):
    for n in names:
        (root / n).mkdir()


# -- resolver ---------------------------------------------------------------------------


def test_exact_prefix_substring_fuzzy(projects_root, cfg):
    mk(projects_root, "Switchers", "pixelforge", "my-todo-app", ".hidden", "node_modules")
    r = discover.resolve_project("switchers", cfg)
    assert isinstance(r, Resolved) and r.name == "Switchers"
    assert discover.resolve_project("pixel", cfg).name == "pixelforge"
    assert discover.resolve_project("todo", cfg).name == "my-todo-app"
    assert discover.resolve_project("pixlforge", cfg).name == "pixelforge"  # fuzzy
    assert isinstance(discover.resolve_project("hidden", cfg), NotFound)
    assert isinstance(discover.resolve_project("node_modules", cfg), NotFound)


def test_ambiguous_and_none(projects_root, cfg):
    mk(projects_root, "api-one", "api-two")
    r = discover.resolve_project("api", cfg)
    assert isinstance(r, Ambiguous) and r.text == "❓ which one? api-one, api-two"
    n = discover.resolve_project("zzzzzz", cfg)
    assert isinstance(n, NotFound)
    assert n.text.startswith("⛔ refused · no project called zzzzzz in ")


def test_configured_project_wins(projects_root, cfg):
    mk(projects_root, "volt")
    r = discover.resolve_project("volt", cfg)
    assert r.detected.kind == "configured" and r.project is cfg.projects["volt"]


def test_comma_list_and_new_dir_seen_at_request_time(tmp_path, monkeypatch, cfg):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv(discover.ENV_VAR, f"{a}, {b}")
    assert isinstance(discover.resolve_project("fresh", cfg), NotFound)
    (b / "fresh").mkdir()
    assert discover.resolve_project("fresh", cfg).name == "fresh"


def test_projects_text_caps_at_20(projects_root, cfg):
    mk(projects_root, *[f"proj{i:02d}" for i in range(25)])
    text = discover.projects_text(cfg)
    names = text.rsplit(": ", 1)[1].split(" (+")[0].split(", ")
    assert len(names) == 20 and "volt" in names and "(+6 more)" in text


def test_ignition_word_match(projects_root):
    mk(projects_root, "pixelforge", "app")
    assert discover.ignition_target("room service, open PixelForge please") == "pixelforge"
    assert discover.ignition_target("room service, pixelforgery") is None
    assert discover.ignition_target("room service app") is None  # < 4 chars
    assert discover.ignition_target("room service", {"room", "service"}) is None


# -- detector ---------------------------------------------------------------------------


def pkg(path, scripts):
    path.mkdir()
    (path / "package.json").write_text(json.dumps({"scripts": scripts}))


def test_detect_npm_and_install(projects_root):
    pkg(projects_root / "web", {"dev": "vite", "start": "x"})
    d = discover.detect("web", projects_root / "web")
    assert d.kind == "node" and d.dev_argv == ["npm", "run", "dev"]
    assert d.install_argv == ["npm", "install"]
    assert d.project.terminals[0].cmd == "npm run dev" and d.project.lights is False
    (projects_root / "web" / "node_modules").mkdir()
    assert discover.detect("web", projects_root / "web").install_argv is None


def test_detect_pnpm_yarn_bun_start(projects_root):
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun")):
        pkg(projects_root / pm, {"dev": "x"})
        (projects_root / pm / lock).write_text("")
        assert discover.detect(pm, projects_root / pm).dev_argv == [pm, "run", "dev"]
    pkg(projects_root / "s", {"start": "node ."})
    assert discover.detect("s", projects_root / "s").dev_argv == ["npm", "run", "start"]


def test_detect_xcode(projects_root):
    p = projects_root / "ios"
    (p / "App.xcodeproj").mkdir(parents=True)
    d = discover.detect("ios", p)
    assert d.kind == "xcode" and d.xcode == p / "App.xcodeproj"
    assert d.project.open_editor is False and not d.project.terminals


def test_detect_python(projects_root):
    p = projects_root / "api"
    p.mkdir()
    (p / "pyproject.toml").write_text("[project]\nname='x'\n")
    (p / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    assert discover.detect("api", p).dev_argv == ["uv", "run", "uvicorn", "main:app", "--reload"]
    q = projects_root / "dj"
    q.mkdir()
    (q / "manage.py").write_text("")
    assert discover.detect("dj", q).dev_argv[-2:] == ["manage.py", "runserver"]


def test_detect_unknown_and_editor_only(projects_root):
    for n, f in (("misc", None), ("rusty", "Cargo.toml"), ("gopher", "go.mod")):
        (projects_root / n).mkdir()
        if f:
            (projects_root / n / f).write_text("")
        d = discover.detect(n, projects_root / n)
        assert d.dev_argv is None and d.project.open_editor and not d.project.terminals


def test_parse_dev_url():
    assert discover.parse_dev_url("  \x1b[32m➜\x1b[0m  Local:   http://localhost:5173/") == (
        "http://localhost:5173"
    )
    assert discover.parse_dev_url("Uvicorn running on http://127.0.0.1:8000") == (
        "http://localhost:8000"
    )
    assert discover.parse_dev_url("ready - https://example.com:3000") is None


# -- desk integration (dry adapter) -----------------------------------------------------


async def test_boot_discovered_project_dry(desk, projects_root):  # noqa: F811
    pkg(projects_root / "newapp", {"dev": "vite"})
    await say(desk, "@hands boot newapp")
    await desk.drain()
    assert any(p.startswith("✅ boot newapp · editor, 1 terminal") for p in posts(desk))
    ops = [c[0] for c in desk.adapter.calls]
    assert "open_in_editor" in ops and "open_terminal" in ops
    assert ("open_terminal" in ops) and desk.adapter.calls[-1][0] != "run"


async def test_boot_unknown_and_ambiguous(desk, projects_root):  # noqa: F811
    mk(projects_root, "api-one", "api-two")
    await say(desk, "@hands boot api")
    await say(desk, "@hands boot nothingatall")
    await desk.drain()
    p = posts(desk)
    assert "❓ which one? api-one, api-two" in p
    assert any(x.startswith("⛔ refused · no project called nothingatall in ") for x in p)


async def test_projects_verb(desk, projects_root):  # noqa: F811
    mk(projects_root, "zeta")
    await say(desk, "@hands projects")
    await desk.drain()
    assert any(x.startswith("✅ projects") and "volt" in x and "zeta" in x for x in posts(desk))


async def test_mission_with_discovered_project(desk, projects_root):  # noqa: F811
    mk(projects_root, "zeta")
    desk.role_room = HQ
    await desk.actions.boot("zeta")
    assert desk.actions._find("zeta")[0] == "zeta"
    await desk.actions._v_mission(["do-it", "zet"], _ctx(desk))
    assert desk.state.active.project == "zeta"
    assert desk.actions.exec_cwd() == projects_root / "zeta"


def _ctx(_d, approved=False):
    from roomservice.desk.actions import ActionContext

    async def up(*a):
        return None

    return ActionContext(HQ, None, "owner", up, approved)


# -- exec -------------------------------------------------------------------------------


def code_of(d):
    text = next(p for p in posts(d) if "approval needed" in p)
    return text.split("ok ")[1].split()[0]


async def test_exec_needs_approval_then_runs(desk, projects_root):  # noqa: F811
    await say(desk, '@hands exec "echo hi && ls -la"')
    await desk.drain()
    ask = next(p for p in posts(desk) if "approval needed" in p)
    assert ask.startswith('⚠️ approval needed · exec "echo hi && ls -la" in ~\n')
    assert not [c for c in desk.adapter.calls if c[0] == "run"]  # nothing ran yet
    await say(desk, f"ok {code_of(desk)}")
    await desk.drain()
    runs = [c for c in desk.adapter.calls if c[0] == "run"]
    assert runs == [("run", (("bash", "-lc", "echo hi && ls -la"), str(projects_root)))]
    assert any(p.startswith("✅ approved by owner · exit 0") for p in posts(desk))


@freeze_time("2026-11-07 10:00:00")
def test_exec_approval_expires_unrun():
    from roomservice.desk.approvals import Approvals

    ap = Approvals(ttl_s=300, publish=lambda e: None)
    a = ap.create('exec "ls"', "r1")
    with freeze_time("2026-11-07 10:06:00"):
        r = ap.resolve(f"ok {a.code}", "o1", "owner", {"o1"})
    assert r.result == "expired"


async def test_exec_deny_and_expiry_never_run(desk):  # noqa: F811
    await say(desk, "@hands exec rm -rf build")
    await desk.drain()
    await say(desk, f"no {code_of(desk)}")
    await desk.drain()
    assert not [c for c in desk.adapter.calls if c[0] == "run"]
    assert any(p.startswith("🚫 declined") for p in posts(desk))


async def test_exec_non_owner_and_agent_refused(desk):  # noqa: F811
    await say(desk, "@hands exec ls", sender="@stranger:srv", name="stranger")
    await say(desk, "@hands exec ls", sender="@bot:srv", name="builder")
    await desk.drain()
    assert not any("approval needed" in p for p in posts(desk))
    assert sum("owner only" in p for p in posts(desk)) >= 1
    assert desk.approvals.open_approvals() == []


async def test_exec_approval_cannot_be_given_by_non_owner_or_agent(desk):  # noqa: F811
    await say(desk, "@hands exec ls")
    await desk.drain()
    code = code_of(desk)
    await say(desk, f"ok {code}", sender="@stranger:srv", name="stranger")
    await say(desk, f"ok {code}", sender="@bot:srv", name="builder")
    await desk.drain()
    assert desk.approvals.get(code) is not None
    assert not [c for c in desk.adapter.calls if c[0] == "run"]


async def test_exec_frozen_refused_and_too_long(desk):  # noqa: F811
    await say(desk, "@hands freeze")
    await say(desk, "@hands exec ls")
    await desk.drain()
    assert "⛔ refused · frozen by owner" in posts(desk)
    await say(desk, "@hands unfreeze")
    await say(desk, "@hands exec " + "x" * 301)
    await desk.drain()
    assert any("longer than 300" in p for p in posts(desk))


async def test_exec_direct_call_without_approval_refuses(desk):  # noqa: F811
    res = await desk.actions.execute(
        __import__("roomservice.desk.grammar", fromlist=["x"]).Command("exec", ["ls"], "exec ls"),
        _ctx(desk, approved=False),
    )
    assert not res.ok and "needs approval" in res.reason


async def test_allowlist_still_refuses_unlisted_app(desk):  # noqa: F811
    await say(desk, "@hands open Steam")
    await desk.drain()
    assert "⛔ refused · open Steam — not on the allowlist" in posts(desk)


async def test_real_shell_runner_and_kill(tmp_path):
    from roomservice.desk.execcmd import ShellRunner

    r = ShellRunner()
    res = await r.run("echo out; echo err >&2; exit 3", tmp_path, 10)
    assert (res.code, res.stdout_tail, res.stderr_tail) == (3, "out", "err")
    import asyncio

    task = asyncio.create_task(r.run("sleep 30", tmp_path, 60))
    await asyncio.sleep(0.3)
    assert r.kill()
    res = await task
    assert res.code == 137
    res = await r.run("sleep 5", tmp_path, 1)
    assert res.code == 124
