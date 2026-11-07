"""Frozen contract (SPEC §8.5): the OS adapter protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel


class RunResult(BaseModel):
    code: int
    stdout_tail: str  # last 15 lines
    stderr_tail: str  # last 15 lines
    ms: int


class OSAdapter(Protocol):
    name: Literal["macos", "windows", "linux", "dry"]

    async def open_app(self, target: str) -> None: ...

    async def quit_app(self, target: str) -> None: ...

    async def open_url(self, url: str) -> None: ...

    async def open_in_editor(self, path: Path) -> None: ...

    async def open_terminal(self, cwd: Path, cmd: str, title: str) -> None: ...

    async def run(self, argv: list[str], cwd: Path, timeout_s: int) -> RunResult: ...

    async def focus(self, on: bool) -> bool:  # False = unsupported
        ...

    async def screenshot_screen(self) -> bytes:  # PNG, primary monitor
        ...

    async def speak(self, text: str, voice: str, rate: int) -> None: ...


def get_adapter(dry_run: bool) -> OSAdapter:
    """Pick the adapter by platform.system(); dry_run forces the dry adapter."""
    # Implemented in roomservice.desk.os (RS-07); re-exported here per SPEC §8.5.
    from roomservice.desk.os import get_adapter as _get_adapter

    return _get_adapter(dry_run)
