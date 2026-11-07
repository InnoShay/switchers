"""`exec` (RS-07): the one place a shell is used (`bash -lc`), only after owner approval.

DECISIONS.md RS-07 documents this exception to SPEC §12.7. The dry adapter never reaches here.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path

from roomservice.contracts.config import ScriptDef
from roomservice.contracts.os import RunResult
from roomservice.desk.os.base import tail

EXEC_MAX_CHARS = 300
EXEC_TIMEOUT_S = ScriptDef(cmd=["x"]).timeout_s  # the ScriptDef default (120)


class ShellRunner:
    """Runs one approved command at a time; `kill()` (called on freeze) stops it."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self.killed = False

    async def run(self, cmd: str, cwd: Path, timeout_s: int = EXEC_TIMEOUT_S) -> RunResult:
        t0 = time.monotonic()
        self.killed = False

        def ms() -> int:
            return int((time.monotonic() - t0) * 1000)

        try:
            proc = await asyncio.create_subprocess_exec(
                "bash",
                "-lc",
                cmd,
                cwd=str(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as e:
            return RunResult(code=127, stdout_tail="", stderr_tail=str(e), ms=ms())
        self._proc = proc
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout_s)
        except TimeoutError:
            self._kill(proc)
            await proc.wait()
            return RunResult(
                code=124, stdout_tail="", stderr_tail=f"timed out after {timeout_s}s", ms=ms()
            )
        except asyncio.CancelledError:
            self._kill(proc)
            raise
        finally:
            self._proc = None
        if self.killed:
            return RunResult(code=137, stdout_tail="", stderr_tail="killed (freeze)", ms=ms())
        return RunResult(
            code=proc.returncode if proc.returncode is not None else 0,
            stdout_tail=tail(out.decode("utf-8", "replace")),
            stderr_tail=tail(err.decode("utf-8", "replace")),
            ms=ms(),
        )

    @staticmethod
    def _kill(proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()

    def kill(self) -> bool:
        if self._proc is None:
            return False
        self.killed = True
        self._kill(self._proc)
        return True
