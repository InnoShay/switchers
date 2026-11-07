"""`roomservice doctor` (SPEC §20.7): every check exists, is isolated, and gives ✅/❌ + a fix.
Everything is mocked: HTTP via respx, machine facts via monkeypatch, no real OS calls."""

from __future__ import annotations

import io
import socket

import httpx
import pytest
import respx
from PIL import Image

from roomservice import doctor as doc
from roomservice import store
from roomservice.agents.desk import add_owner
from roomservice.contracts.config import Settings

SW = "http://sw.test"
N8N = "http://n8n.test/webhook/roomservice-life"

EXPECTED = [
    "switch_health",
    "registration_key",
    "agents_json",
    "agent_keys",
    "rooms_visible",
    "owners_paired",
    "desk_yaml",
    "project_paths",
    "code_on_path",
    "apps_installed",
    "screen_recording",
    "shortcuts",
    "n8n",
    "playwright",
    "tts",
    "hud_port",
]


def png(color: tuple[int, int, int], lit_fraction: float = 0.0) -> bytes:
    img = Image.new("RGB", (320, 200), color)
    if lit_fraction:
        h = int(200 * lit_fraction)
        img.paste((255, 255, 255), (0, 0, 320, h))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def desk_yaml(fixtures_dir, tmp_path):
    proj = tmp_path / "volt"
    proj.mkdir()
    text = (fixtures_dir / "desk_example.yaml").read_text()
    text = text.replace("~/roomservice-workspace/projects/volt", str(proj))
    path = tmp_path / "desk.yaml"
    path.write_text(text)
    return path


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("SWITCH_URL", SW)
    monkeypatch.setenv("SWITCH_REGISTRATION_KEY", "reg-key")
    monkeypatch.setenv("N8N_LIFE_URL", N8N)
    monkeypatch.setenv("N8N_LIFE_TOKEN", "n8n-token")
    return Settings(_env_file=None)


@pytest.fixture
def machine(monkeypatch):
    """A healthy Mac with everything installed."""
    monkeypatch.setattr(doc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(doc.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(doc, "mac_app_installed", lambda name: True)
    monkeypatch.setattr(doc, "playwright_chromium_installed", lambda: True)

    class Adapter:
        async def screenshot_screen(self):
            return png((20, 20, 30), lit_fraction=0.5)

    monkeypatch.setattr("roomservice.desk.os.get_adapter", lambda dry: Adapter())

    class Proc:
        async def communicate(self):
            return b"RoomService Focus On\nRoomService Focus Off\nOther", b""

    async def fake_exec(*a, **k):
        return Proc()

    monkeypatch.setattr(doc.asyncio, "create_subprocess_exec", fake_exec)


def healthy_switch():
    respx.get(f"{SW}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    respx.get(f"{SW}/agents/id-d/ops").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{SW}/agents/id-l/ops").mock(return_value=httpx.Response(200, json={}))
    respx.post(f"{SW}/agents/id-d/ops/list_rooms").mock(
        return_value=httpx.Response(
            200,
            json={"result": [{"id": "r1", "name": "roomservice-hq"}, {"id": "r2", "name": "x"}]},
        )
    )
    respx.post(N8N).mock(return_value=httpx.Response(200, json={"reply": "pong"}))


@pytest.fixture
def paired():
    store.save_agent_creds(SW, "desk-laptop", "id-d", "key-d")
    store.save_agent_creds(SW, "life", "id-l", "key-l")
    add_owner("@owner:srv", "owner", "roomservice-hq")


def by_name(results):
    return {r.name: r for r in results}


def test_checks_list_is_complete(settings, desk_yaml):
    d = doc.Doctor(settings, desk_yaml)
    assert [c.__name__ for c in d.checks()] == EXPECTED


@respx.mock
async def test_everything_green(settings, desk_yaml, machine, paired, monkeypatch):
    healthy_switch()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free = sock.getsockname()[1]
    monkeypatch.setenv("HUD_PORT", str(free))
    s = Settings(_env_file=None)
    results = await doc.run_doctor(s, desk_yaml)
    assert len(results) == len(EXPECTED)
    bad = [doc.format_result(r) for r in results if not r.ok]
    assert bad == []
    rooms = by_name(results)["Rooms visible"]
    assert "roomservice-hq [HQ]" in rooms.detail and "x [HQ]" not in rooms.detail
    # the n8n probe is exactly the spec'd body + token header
    req = next(c.request for c in respx.calls if str(c.request.url) == N8N)
    assert req.headers["X-RoomService-Token"] == "n8n-token"
    assert b'"mode":"ask"' in req.content.replace(b" ", b"") and b"ping" in req.content


def test_format_result_shows_mark_detail_and_fix():
    ok = doc.format_result(doc.CheckResult("A", True, "fine"))
    bad = doc.format_result(doc.CheckResult("B", False, "broke", "do this"))
    assert ok == "✅ A — fine"
    assert bad == "❌ B — broke\n     fix: do this"


@respx.mock
async def test_every_failure_has_a_fix_hint(settings, tmp_path, monkeypatch):
    """Nothing works at all: every check is ❌ with a non-empty hint and none crashes the run."""
    respx.get(f"{SW}/health").mock(side_effect=httpx.ConnectError("down"))
    respx.post(N8N).mock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(doc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(doc.shutil, "which", lambda name: None)
    monkeypatch.setattr(doc, "mac_app_installed", lambda name: False)
    monkeypatch.setattr(doc, "playwright_chromium_installed", lambda: False)

    class Blank:
        async def screenshot_screen(self):
            return png((0, 0, 0))

    monkeypatch.setattr("roomservice.desk.os.get_adapter", lambda dry: Blank())

    async def no_shortcuts(*a, **k):
        raise FileNotFoundError("shortcuts")

    monkeypatch.setattr(doc.asyncio, "create_subprocess_exec", no_shortcuts)
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    monkeypatch.setenv("HUD_PORT", str(busy.getsockname()[1]))
    monkeypatch.delenv("SWITCH_REGISTRATION_KEY")
    try:
        results = await doc.run_doctor(Settings(_env_file=None), tmp_path / "missing.yaml")
    finally:
        busy.close()
    assert len(results) == len(EXPECTED)
    for r in results:
        assert not r.ok, r
        assert r.hint, f"{r.name} has no fix hint"
        assert "\n     fix: " in doc.format_result(r)


@respx.mock
async def test_switch_health_ok_and_down(settings, desk_yaml):
    d = doc.Doctor(settings, desk_yaml)
    respx.get(f"{SW}/health").mock(return_value=httpx.Response(200))
    assert (await d.switch_health()).ok
    respx.get(f"{SW}/health").mock(return_value=httpx.Response(503))
    r = await d.switch_health()
    assert not r.ok and "SWITCH_URL" in r.hint


async def test_registration_key_missing_vs_set(monkeypatch, desk_yaml):
    monkeypatch.setenv("SWITCH_URL", SW)
    monkeypatch.delenv("SWITCH_REGISTRATION_KEY", raising=False)
    r = await doc.Doctor(Settings(_env_file=None), desk_yaml).registration_key()
    assert not r.ok and "API Keys" in r.hint
    monkeypatch.setenv("SWITCH_REGISTRATION_KEY", "k")
    r = await doc.Doctor(Settings(_env_file=None), desk_yaml).registration_key()
    assert r.ok


@respx.mock
async def test_agents_json_and_agent_keys(settings, desk_yaml):
    d = doc.Doctor(settings, desk_yaml)
    r = await d.agents_json()
    assert not r.ok and "register" in r.hint
    r = await d.agent_keys()
    assert not r.ok and "register" in r.hint
    store.save_agent_creds(SW, "desk-laptop", "id-d", "key-d")
    store.save_agent_creds(SW, "life", "id-l", "key-l")
    assert (await d.agents_json()).ok
    respx.get(f"{SW}/agents/id-d/ops").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{SW}/agents/id-l/ops").mock(return_value=httpx.Response(401))
    r = await d.agent_keys()
    assert not r.ok and "life" in r.detail and "desk-laptop" not in r.detail
    assert "--overwrite" in r.hint
    assert "key-l" not in r.detail  # never echo keys


@respx.mock
async def test_rooms_visible_marks_hq_and_flags_missing_hq(settings, desk_yaml):
    d = doc.Doctor(settings, desk_yaml)
    assert not (await d.rooms_visible()).ok  # no credentials yet
    store.save_agent_creds(SW, "desk-laptop", "id-d", "key-d")
    route = respx.post(f"{SW}/agents/id-d/ops/list_rooms")
    route.mock(return_value=httpx.Response(200, json={"result": [{"id": "r2", "name": "other"}]}))
    r = await d.rooms_visible()
    assert not r.ok and "!invite-agent" in r.hint
    route.mock(
        return_value=httpx.Response(
            200,
            json={"result": [{"id": "r1", "name": "RoomService HQ"}, {"id": "r2", "name": "m"}]},
        )
    )
    r = await d.rooms_visible()
    assert r.ok and "RoomService HQ [HQ]" in r.detail and "m [HQ]" not in r.detail
    route.mock(return_value=httpx.Response(500))
    r = await d.rooms_visible()  # Switch error: still a ❌ line with a fix, not a crash
    assert not r.ok and r.hint


async def test_owners_paired(settings, desk_yaml):
    d = doc.Doctor(settings, desk_yaml)
    r = await d.owners_paired()
    assert not r.ok and "roomservice pair" in r.hint
    add_owner("@o:srv", "o", "hq")
    add_owner("@o2:srv", "o", "tg")
    r = await d.owners_paired()
    assert r.ok and "2 owner" in r.detail


async def test_desk_yaml_and_project_paths(settings, desk_yaml, tmp_path):
    ok = doc.Doctor(settings, desk_yaml)
    assert (await ok.desk_yaml()).ok and (await ok.project_paths()).ok
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: 1\nmachine_name: [oops")
    d = doc.Doctor(settings, broken)
    r = await d.desk_yaml()
    assert not r.ok and "desk.example.yaml" in r.hint
    r = await d.project_paths()
    assert not r.ok and "desk.yaml" in r.hint  # degrades instead of raising
    # valid yaml but the project folder is gone
    gone = tmp_path / "gone.yaml"
    gone.write_text(desk_yaml.read_text().replace(str(tmp_path / "volt"), str(tmp_path / "nope")))
    r = await doc.Doctor(settings, gone).project_paths()
    assert not r.ok and "volt" in r.detail and "setup_mac.sh" in r.hint


async def test_code_on_path(settings, desk_yaml, monkeypatch):
    d = doc.Doctor(settings, desk_yaml)
    monkeypatch.setattr(
        doc.shutil, "which", lambda n: "/usr/local/bin/code" if n == "code" else None
    )
    assert (await d.code_on_path()).ok
    monkeypatch.setattr(doc.shutil, "which", lambda n: None)
    r = await d.code_on_path()
    assert not r.ok and "Shell Command" in r.hint


async def test_browser_and_spotify_mac_and_linux(settings, desk_yaml, monkeypatch):
    d = doc.Doctor(settings, desk_yaml)
    monkeypatch.setattr(doc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(doc, "mac_app_installed", lambda n: n == "Google Chrome")
    r = await d.apps_installed()
    assert not r.ok and "Spotify" in r.detail and "browser" not in r.detail
    monkeypatch.setattr(doc, "mac_app_installed", lambda n: n in ("Brave Browser", "Spotify"))
    assert (await d.apps_installed()).ok  # any browser counts, e.g. Brave
    monkeypatch.setattr(doc, "mac_app_installed", lambda n: True)
    assert (await d.apps_installed()).ok
    monkeypatch.setattr(doc.platform, "system", lambda: "Linux")
    monkeypatch.setattr(doc.shutil, "which", lambda n: "/x" if n == "spotify" else None)
    r = await d.apps_installed()
    assert not r.ok and "browser" in r.detail
    monkeypatch.setattr(
        doc.shutil, "which", lambda n: "/x" if n in ("spotify", "brave-browser") else None
    )
    assert (await d.apps_installed()).ok


@pytest.mark.parametrize(
    "image,ok",
    [
        (png((0, 0, 0)), False),  # permission denied -> black screen
        (png((20, 20, 30), lit_fraction=0.01), False),  # 1% lit: below the 2% line
        (png((20, 20, 30), lit_fraction=0.05), True),  # 5% lit
        (png((200, 200, 200)), True),
    ],
)
async def test_screen_recording_heuristic(settings, desk_yaml, monkeypatch, image, ok):
    class A:
        async def screenshot_screen(self):
            return image

    monkeypatch.setattr("roomservice.desk.os.get_adapter", lambda dry: A())
    r = await doc.Doctor(settings, desk_yaml).screen_recording()
    assert r.ok is ok
    if not ok:
        assert "Screen Recording" in r.hint


def test_non_dark_fraction_math():
    assert doc.non_dark_fraction(png((0, 0, 0))) == 0
    assert doc.non_dark_fraction(png((255, 255, 255))) == 1
    assert 0.45 < doc.non_dark_fraction(png((0, 0, 0), lit_fraction=0.5)) < 0.55


async def test_screen_recording_exception_is_isolated(settings, desk_yaml, monkeypatch):
    class Boom:
        async def screenshot_screen(self):
            raise OSError("no display")

    monkeypatch.setattr("roomservice.desk.os.get_adapter", lambda dry: Boom())
    results = await doc.Doctor(settings, desk_yaml).run()
    sr = next(r for r in results if r.name == "screen recording")
    assert not sr.ok and "OSError" in sr.detail and sr.hint


async def test_shortcuts_present_missing_and_non_mac(settings, desk_yaml, monkeypatch):
    d = doc.Doctor(settings, desk_yaml)

    def fake(out: bytes):
        class P:
            async def communicate(self):
                return out, b""

        async def ex(*a, **k):
            return P()

        monkeypatch.setattr(doc.asyncio, "create_subprocess_exec", ex)

    monkeypatch.setattr(doc.platform, "system", lambda: "Darwin")
    fake(b"RoomService Focus On\nRoomService Focus Off\n")
    assert (await d.shortcuts()).ok
    fake(b"RoomService Focus On\n")
    r = await d.shortcuts()
    assert not r.ok and "Focus Off" in r.detail and "Set Focus" in r.hint
    monkeypatch.setattr(doc.platform, "system", lambda: "Linux")
    assert (await d.shortcuts()).ok  # n/a off macOS


@respx.mock
async def test_n8n_reachable_token_and_down(settings, desk_yaml):
    d = doc.Doctor(settings, desk_yaml)
    respx.post(N8N).mock(return_value=httpx.Response(200, json={}))
    assert (await d.n8n()).ok
    respx.post(N8N).mock(return_value=httpx.Response(403))
    r = await d.n8n()
    assert not r.ok and "403" in r.detail and "N8N_LIFE_TOKEN" in r.hint
    respx.post(N8N).mock(side_effect=httpx.ConnectError("refused"))
    r = await d.n8n()
    assert not r.ok and "docker compose" in r.hint
    assert "n8n-token" not in r.detail + r.hint  # token never shown


async def test_playwright_tts_and_hud_port(settings, desk_yaml, monkeypatch):
    d = doc.Doctor(settings, desk_yaml)
    monkeypatch.setattr(doc, "playwright_chromium_installed", lambda: False)
    r = await d.playwright()
    assert not r.ok and "playwright install chromium" in r.hint
    monkeypatch.setattr(doc, "playwright_chromium_installed", lambda: True)
    assert (await d.playwright()).ok

    monkeypatch.setattr(doc.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(doc.shutil, "which", lambda n: None)
    r = await d.tts()
    assert not r.ok and "`say`" in r.detail and r.hint
    monkeypatch.setattr(doc.shutil, "which", lambda n: "/usr/bin/say")
    assert (await d.tts()).ok

    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen()
    monkeypatch.setenv("HUD_PORT", str(busy.getsockname()[1]))
    d2 = doc.Doctor(Settings(_env_file=None), desk_yaml)
    try:
        r = await d2.hud_port()
        assert not r.ok and "in use" in r.detail and "HUD_PORT" in r.hint
    finally:
        busy.close()
    assert (await d2.hud_port()).ok


def test_playwright_detection_uses_env_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    monkeypatch.setattr(doc.Path, "home", classmethod(lambda cls: tmp_path / "nohome"))
    assert not doc.playwright_chromium_installed()
    (tmp_path / "chromium-1100").mkdir()
    assert doc.playwright_chromium_installed()


def test_cli_doctor_exit_code_and_output(monkeypatch):
    from typer.testing import CliRunner

    from roomservice import cli

    async def fake_run(settings, desk_config_path=None):
        return [doc.CheckResult("A", True, "ok"), doc.CheckResult("B", False, "bad", "fix it")]

    monkeypatch.setenv("SWITCH_URL", SW)
    monkeypatch.setattr(doc, "run_doctor", fake_run)
    res = CliRunner().invoke(cli.app, ["doctor"])
    assert res.exit_code == 1
    assert "✅ A — ok" in res.output and "❌ B — bad" in res.output and "fix: fix it" in res.output
