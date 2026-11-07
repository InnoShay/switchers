"""Windows adapter (SPEC §12.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from roomservice.contracts.os import RunResult
from roomservice.desk.os import base


class WindowsAdapter:
    name: Literal["windows"] = "windows"

    async def open_app(self, target: str) -> None:
        await base.exec_ok(["cmd", "/c", "start", "", target])

    async def quit_app(self, target: str) -> None:
        exe = target if target.lower().endswith(".exe") else f"{target}.exe"
        await base.exec_ok(["taskkill", "/IM", exe, "/F"])

    async def open_url(self, url: str) -> None:
        # not `cmd /c start`: cmd would treat `&`, `|`, `^` inside the URL as command separators
        await base.exec_ok(["rundll32", "url.dll,FileProtocolHandler", url])

    async def open_in_editor(self, path: Path) -> None:
        await base.exec_ok(["code.cmd", str(path)])

    async def open_terminal(self, cwd: Path, cmd: str, title: str) -> None:
        await base.exec_ok(["wt", "-d", str(cwd), "cmd", "/k", cmd])

    async def run(self, argv: list[str], cwd: Path, timeout_s: int) -> RunResult:
        return await base.exec_run(argv, cwd, timeout_s)

    async def focus(self, on: bool) -> bool:
        return False

    async def screenshot_screen(self) -> bytes:
        return await base.screenshot_primary()

    async def speak(self, text: str, voice: str, rate: int) -> None:
        # PowerShell also treats the typographic single quotes as string delimiters
        safe = text
        for q in "'\u2018\u2019\u201a\u201b":
            safe = safe.replace(q, q + q)
        script = (
            "Add-Type -AssemblyName System.Speech; "
            f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe}')"
        )
        await base.exec_ok(["powershell", "-NoProfile", "-Command", script], timeout_s=60)
