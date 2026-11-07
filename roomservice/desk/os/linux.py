"""Linux adapter (SPEC §12.7)."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Literal

from roomservice.contracts.os import RunResult
from roomservice.desk.os import base


class LinuxAdapter:
    name: Literal["linux"] = "linux"

    async def open_app(self, target: str) -> None:
        await base.spawn_detached([target])

    async def quit_app(self, target: str) -> None:
        await base.exec_ok(["pkill", "-f", target])

    async def open_url(self, url: str) -> None:
        await base.exec_ok(["xdg-open", url])

    async def open_in_editor(self, path: Path) -> None:
        await base.exec_ok(["code", str(path)])

    async def open_terminal(self, cwd: Path, cmd: str, title: str) -> None:
        line = f"cd {shlex.quote(str(cwd))} && {cmd}; exec bash"
        await base.spawn_detached(["x-terminal-emulator", "-e", "bash", "-lc", line])

    async def run(self, argv: list[str], cwd: Path, timeout_s: int) -> RunResult:
        return await base.exec_run(argv, cwd, timeout_s)

    async def focus(self, on: bool) -> bool:
        return False

    async def screenshot_screen(self) -> bytes:
        return await base.screenshot_primary()

    async def speak(self, text: str, voice: str, rate: int) -> None:
        await base.exec_ok(["espeak", text], timeout_s=60)
