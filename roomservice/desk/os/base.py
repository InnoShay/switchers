"""Shared subprocess + screenshot helpers for the OS adapters (SPEC §12.7).

Everything goes through asyncio.create_subprocess_exec with an argv list: never a shell.
"""

from __future__ import annotations

import asyncio
import io
import time
from pathlib import Path

from roomservice.contracts.os import RunResult
from roomservice.log import get_logger

log = get_logger("os")

TAIL_LINES = 15


class AdapterError(RuntimeError):
    """An OS operation failed (non-zero exit or missing binary)."""


def tail(text: str, n: int = TAIL_LINES) -> str:
    return "\n".join(text.splitlines()[-n:])


async def exec_run(argv: list[str], cwd: Path | None, timeout_s: int) -> RunResult:
    """Run argv, capture output. Missing binary -> code 127, timeout -> code 124."""
    t0 = time.monotonic()

    def ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, PermissionError, NotADirectoryError) as e:
        return RunResult(code=127, stdout_tail="", stderr_tail=str(e), ms=ms())
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return RunResult(
            code=124, stdout_tail="", stderr_tail=f"timed out after {timeout_s}s", ms=ms()
        )
    return RunResult(
        code=proc.returncode if proc.returncode is not None else 0,
        stdout_tail=tail(out.decode("utf-8", "replace")),
        stderr_tail=tail(err.decode("utf-8", "replace")),
        ms=ms(),
    )


async def exec_ok(argv: list[str], timeout_s: int = 30) -> RunResult:
    """exec_run that raises AdapterError on a non-zero exit."""
    res = await exec_run(argv, None, timeout_s)
    if res.code != 0:
        raise AdapterError(f"{argv[0]} exited {res.code}: {res.stderr_tail or res.stdout_tail}")
    return res


async def spawn_detached(argv: list[str]) -> None:
    """Start a long-lived program without waiting for it (Linux open_app / terminal)."""
    try:
        await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except (FileNotFoundError, PermissionError) as e:
        raise AdapterError(str(e)) from e


def _grab_png() -> bytes:
    import mss
    import mss.tools

    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        shot = sct.grab(mon)
        return mss.tools.to_png(shot.rgb, shot.size) or b""


async def screenshot_primary() -> bytes:
    """mss monitor 1 -> PNG bytes (same on every OS)."""
    return await asyncio.to_thread(_grab_png)


def png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
