"""Speech queue (SPEC §12, §8.5). Calls an injected adapter's speak(); no OS calls here."""

from __future__ import annotations

import asyncio
from typing import Protocol

from roomservice.contracts.config import Voice
from roomservice.log import get_logger

log = get_logger("voice")

MAX_TEXT = 200  # `say` limit (SPEC §12.3)
MAX_PENDING = 10


class Speaker(Protocol):
    async def speak(self, text: str, voice: str, rate: int) -> None: ...


class SpeechQueue:
    """Serial, non-blocking speech: `say()` returns immediately; a worker speaks in order."""

    def __init__(self, adapter: Speaker, voice: Voice | None = None) -> None:
        self._adapter = adapter
        self._voice = voice or Voice()
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def say(self, text: str) -> bool:
        """Queue `text`. False if speech is disabled or the text is empty. Drops the oldest
        queued line when more than MAX_PENDING are waiting."""
        text = " ".join(text.split())[:MAX_TEXT]
        if not self._voice.enabled or not text:
            return False
        while self._queue.qsize() >= MAX_PENDING:
            self._queue.get_nowait()
            self._queue.task_done()
        self._queue.put_nowait(text)
        return True

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def drain(self) -> None:
        """Wait until everything queued so far has been spoken."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                await self._adapter.speak(text, self._voice.voice_name, self._voice.rate)
            except Exception as e:  # speech must never take the desk down
                log.warning("speak failed: %s", e)
            finally:
                self._queue.task_done()
