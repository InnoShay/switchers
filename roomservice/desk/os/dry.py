"""Dry-run adapter (SPEC §12.4): logs, sleeps 150 ms, succeeds. No OS side effects."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Literal

from roomservice.contracts.os import RunResult
from roomservice.desk.os.base import png_bytes
from roomservice.log import get_logger

log = get_logger("os.dry")

DELAY_S = 0.15


class DryAdapter:
    name: Literal["dry"] = "dry"

    def __init__(self, delay_s: float = DELAY_S) -> None:
        self.delay_s = delay_s
        self.calls: list[tuple[str, tuple]] = []
        self.verb = "shot"  # set by the desk before each command; shown in screenshots

    async def _do(self, op: str, *args) -> None:
        self.calls.append((op, args))
        log.info("dry-run %s %s", op, args)
        await asyncio.sleep(self.delay_s)

    async def open_app(self, target: str) -> None:
        await self._do("open_app", target)

    async def quit_app(self, target: str) -> None:
        await self._do("quit_app", target)

    async def open_url(self, url: str) -> None:
        await self._do("open_url", url)

    async def open_in_editor(self, path: Path) -> None:
        await self._do("open_in_editor", str(path))

    async def open_terminal(self, cwd: Path, cmd: str, title: str) -> None:
        await self._do("open_terminal", str(cwd), cmd, title)

    async def run(self, argv: list[str], cwd: Path, timeout_s: int) -> RunResult:
        await self._do("run", tuple(argv), str(cwd))
        return RunResult(code=0, stdout_tail=f"dry run: {' '.join(argv)}", stderr_tail="", ms=150)

    async def focus(self, on: bool) -> bool:
        await self._do("focus", on)
        return True

    async def screenshot_screen(self) -> bytes:
        await self._do("screenshot_screen")
        return make_dry_png(self.verb)

    async def speak(self, text: str, voice: str, rate: int) -> None:
        await self._do("speak", text)


def make_dry_png(verb: str, when: datetime | None = None) -> bytes:
    """1280x800 dark PNG with `DRY RUN · <verb> · HH:MM:SS`."""
    from PIL import Image, ImageDraw, ImageFont

    when = when or datetime.now()
    img = Image.new("RGB", (1280, 800), (14, 16, 22))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # older Pillow
        font = ImageFont.load_default()
    text = f"DRY RUN · {verb} · {when:%H:%M:%S}"
    box = draw.textbbox((0, 0), text, font=font)
    x = (1280 - (box[2] - box[0])) / 2
    y = (800 - (box[3] - box[1])) / 2
    draw.text((x, y), text, fill=(245, 247, 250), font=font)
    return png_bytes(img)
