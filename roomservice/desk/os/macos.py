"""macOS adapter (SPEC §12.7)."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

from roomservice.contracts.os import RunResult
from roomservice.desk.os import base


def applescript_str(s: str) -> str:
    """Escape for use inside an AppleScript double-quoted string."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


class MacOSAdapter:
    name: Literal["macos"] = "macos"

    async def open_app(self, target: str) -> None:
        await base.exec_ok(["open", "-a", target])

    async def quit_app(self, target: str) -> None:
        await base.exec_ok(["osascript", "-e", f'quit app "{applescript_str(target)}"'])

    async def open_url(self, url: str) -> None:
        await base.exec_ok(["open", url])

    async def open_in_editor(self, path: Path) -> None:
        await base.exec_ok(["code", str(path)])

    async def open_terminal(self, cwd: Path, cmd: str, title: str) -> None:
        line = f"cd {shlex.quote(str(cwd))} && {cmd}"
        await base.exec_ok(
            [
                "osascript",
                "-e",
                f'tell application "Terminal" to do script "{applescript_str(line)}"',
                "-e",
                'tell application "Terminal" to activate',
            ]
        )

    async def run(self, argv: list[str], cwd: Path, timeout_s: int) -> RunResult:
        return await base.exec_run(argv, cwd, timeout_s)

    async def focus(self, on: bool) -> bool:
        shortcut = "RoomService Focus On" if on else "RoomService Focus Off"
        res = await base.exec_run(["shortcuts", "run", shortcut], None, 20)
        return res.code == 0

    async def screenshot_screen(self) -> bytes:
        return await base.screenshot_primary()

    async def speak(self, text: str, voice: str, rate: int) -> None:
        await base.exec_ok(["say", "-v", voice, "-r", str(rate), text], timeout_s=60)
