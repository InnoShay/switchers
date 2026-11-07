"""OS adapters (SPEC §12.7, §20.2): argv per OS with subprocess mocked; q() quoting."""

import asyncio
import shlex
from pathlib import Path

import pytest

from roomservice.desk.os import base, get_adapter
from roomservice.desk.os.dry import DryAdapter, make_dry_png
from roomservice.desk.os.linux import LinuxAdapter
from roomservice.desk.os.macos import MacOSAdapter
from roomservice.desk.os.windows import WindowsAdapter


class FakeProc:
    def __init__(self, code=0, out=b"", err=b""):
        self.returncode = code
        self._out, self._err = out, err

    async def communicate(self):
        return self._out, self._err

    def kill(self):
        pass

    async def wait(self):
        return self.returncode


@pytest.fixture
def calls(monkeypatch):
    class Rec(list):
        state: dict

    rec = Rec()
    state = {"code": 0, "out": b"", "err": b""}

    async def fake_exec(*argv, **kw):
        rec.append(tuple(argv))
        return FakeProc(state["code"], state["out"], state["err"])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    rec.state = state
    return rec


async def test_macos_argv(calls):
    a = MacOSAdapter()
    await a.open_app("Google Chrome")
    await a.quit_app("Spotify")
    await a.open_url("https://github.com")
    await a.open_in_editor(Path("/tmp/my proj"))
    await a.speak("hello there", "Samantha", 190)
    assert calls == [
        ("open", "-a", "Google Chrome"),
        ("osascript", "-e", 'quit app "Spotify"'),
        ("open", "https://github.com"),
        ("code", "/tmp/my proj"),
        ("say", "-v", "Samantha", "-r", "190", "hello there"),
    ]


async def test_macos_terminal_quotes_cwd(calls):
    await MacOSAdapter().open_terminal(Path("/tmp/my proj"), "npm run dev", "dev")
    argv = calls[0]
    assert argv[0] == "osascript"
    quoted = shlex.quote("/tmp/my proj")
    assert argv[2] == f'tell application "Terminal" to do script "cd {quoted} && npm run dev"'
    assert argv[4] == 'tell application "Terminal" to activate'


async def test_macos_applescript_escaping(calls):
    await MacOSAdapter().quit_app('Evil" & do shell script "x')
    assert calls[0][2] == 'quit app "Evil\\" & do shell script \\"x"'


async def test_macos_focus_uses_shortcuts_and_reports_failure(calls):
    a = MacOSAdapter()
    assert await a.focus(True) is True
    assert calls[-1] == ("shortcuts", "run", "RoomService Focus On")
    calls.state["code"] = 1
    assert await a.focus(False) is False
    assert calls[-1] == ("shortcuts", "run", "RoomService Focus Off")


async def test_windows_argv(calls):
    a = WindowsAdapter()
    await a.open_app("spotify")
    await a.quit_app("spotify")
    await a.quit_app("code.exe")
    await a.open_url("https://github.com")
    await a.open_in_editor(Path("C:/p"))
    await a.open_terminal(Path("C:/p"), "npm run dev", "dev")
    await a.speak("it's ok", "Samantha", 190)
    assert calls[:6] == [
        ("cmd", "/c", "start", "", "spotify"),
        ("taskkill", "/IM", "spotify.exe", "/F"),
        ("taskkill", "/IM", "code.exe", "/F"),
        ("cmd", "/c", "start", "", "https://github.com"),
        ("code.cmd", str(Path("C:/p"))),
        ("wt", "-d", str(Path("C:/p")), "cmd", "/k", "npm run dev"),
    ]
    ps = calls[6]
    assert ps[:3] == ("powershell", "-NoProfile", "-Command")
    assert "Speak('it''s ok')" in ps[3]
    assert await a.focus(True) is False


async def test_linux_argv(calls):
    a = LinuxAdapter()
    await a.open_app("gedit")
    await a.quit_app("spotify")
    await a.open_url("https://github.com")
    await a.open_in_editor(Path("/tmp/p"))
    await a.open_terminal(Path("/tmp/my proj"), "npm run dev", "dev")
    await a.speak("hello", "x", 1)
    assert calls == [
        ("gedit",),
        ("pkill", "-f", "spotify"),
        ("xdg-open", "https://github.com"),
        ("code", "/tmp/p"),
        (
            "x-terminal-emulator",
            "-e",
            "bash",
            "-lc",
            f"cd {shlex.quote('/tmp/my proj')} && npm run dev; exec bash",
        ),
        ("espeak", "hello"),
    ]
    assert await a.focus(True) is False


async def test_run_returns_tails_and_exit_code(calls):
    calls.state.update(code=3, out=b"\n".join(f"l{i}".encode() for i in range(30)), err=b"boom")
    res = await LinuxAdapter().run(["npm", "test"], Path("/tmp"), 5)
    assert calls[0] == ("npm", "test")
    assert res.code == 3
    assert res.stdout_tail.splitlines() == [f"l{i}" for i in range(15, 30)]
    assert res.stderr_tail == "boom"


async def test_failed_command_raises_adapter_error(calls):
    calls.state.update(code=1, err=b"nope")
    with pytest.raises(base.AdapterError, match="nope"):
        await MacOSAdapter().open_app("Missing")


async def test_missing_binary_is_code_127(monkeypatch):
    async def boom(*a, **k):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", boom)
    res = await base.exec_run(["nothing"], None, 1)
    assert res.code == 127


async def test_dry_adapter_succeeds_and_records():
    a = DryAdapter(delay_s=0)
    await a.open_app("x")
    assert await a.focus(True) is True
    res = await a.run(["git", "status"], Path("/tmp"), 5)
    assert res.code == 0
    a.verb = "boot"
    png = await a.screenshot_screen()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert [c[0] for c in a.calls] == ["open_app", "focus", "run", "screenshot_screen"]


def test_dry_png_is_1280x800():
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(make_dry_png("shot")))
    assert img.size == (1280, 800)


@pytest.mark.parametrize(
    "system,cls", [("Darwin", MacOSAdapter), ("Windows", WindowsAdapter), ("Linux", LinuxAdapter)]
)
def test_get_adapter_by_platform(monkeypatch, system, cls):
    monkeypatch.setattr("platform.system", lambda: system)
    assert isinstance(get_adapter(False), cls)
    assert get_adapter(True).name == "dry"
