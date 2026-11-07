"""Ignition (SPEC §12.9): a paired owner's wake phrase in an HQ room boots the desk.

`matches()` is pure (used by wants_unaddressed); `fire()` dedupes, enforces the 60 s cooldown,
then: HUD event first, lights webhook, speak, receipt, enqueue `boot` (first visible action
well inside 3 s).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from roomservice.bus import bus as default_bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import DeskConfig, Settings
from roomservice.contracts.events import IgnitionEvent
from roomservice.contracts.switch import MessagePayload
from roomservice.desk import receipts
from roomservice.desk.grammar import Command
from roomservice.log import get_logger

log = get_logger("desk.ignition")

COOLDOWN_S = 60.0
SEEN_MAX = 500


def normalize(text: str) -> str:
    """Lowercase, punctuation stripped, whitespace collapsed, padded with single spaces."""
    words = re.sub(r"[^\w]+", " ", text.casefold().replace("_", " ")).split()
    return " " + " ".join(words) + " "


def greeting(now: datetime) -> str:
    h = now.hour
    if 5 <= h <= 11:
        return "Morning"
    if 12 <= h <= 16:
        return "Afternoon"
    return "Evening"


class Ignition:
    def __init__(
        self,
        cfg: DeskConfig,
        settings: Settings,
        *,
        owner_ids: Callable[[], set[str]],
        post: Callable[[RoomInfo, str], Awaitable[None]],
        speak: Callable[[str], None],
        enqueue: Callable[[Command, RoomInfo], None],
        lights_webhook: Callable[[], Awaitable[Any]] | None = None,
        on_ignite: Callable[[], None] | None = None,
        bus: Any = default_bus,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.cfg = cfg
        self.settings = settings
        self._owner_ids = owner_ids
        self._post = post
        self._speak = speak
        self._enqueue = enqueue
        self._lights_webhook = lights_webhook
        self._on_ignite = on_ignite
        self.bus = bus
        self._clock = clock
        self._now = now or (lambda: datetime.now(receipts.IST))
        self._last: float | None = None
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._phrases = [normalize(p) for p in cfg.ignition.wake_phrases if p.strip()]

    # -- pure checks --------------------------------------------------------------------

    def matches(self, room: RoomInfo, msg: MessagePayload) -> bool:
        """HQ + paired owner + wake phrase. No side effects."""
        if room.kind != RoomKind.HQ or msg.sender not in self._owner_ids():
            return False
        body = normalize(msg.body)
        return any(p in body for p in self._phrases)

    def pick_target(self, body: str) -> str:
        """First project (config order) with a keyword in the body, else the default profile."""
        text = normalize(body)
        for name, proj in self.cfg.projects.items():
            for kw in proj.keywords:
                k = normalize(kw)
                if k.strip() and k in text:
                    return name
        return self.cfg.ignition.default_profile

    # -- action -------------------------------------------------------------------------

    def _suppressed(self, message_id: str) -> str | None:
        if message_id in self._seen:
            return "duplicate"
        self._seen[message_id] = None
        if len(self._seen) > SEEN_MAX:
            self._seen.popitem(last=False)
        if self._last is not None and self._clock() - self._last < COOLDOWN_S:
            return "cooldown"
        return None

    async def fire(self, room: RoomInfo, msg: MessagePayload) -> str | None:
        """Run ignition. Returns the target booted, or None if suppressed."""
        why = self._suppressed(msg.message_id)
        if why:
            log.info("ignition suppressed (%s)", why, extra={"room": room.name})
            return None
        self._last = self._clock()
        target = self.pick_target(msg.body)
        mode = "webhook" if self.settings.lights_on_url else "flash"
        self.bus.publish(IgnitionEvent(project=target, lights=mode))  # first visible action
        if self._on_ignite:
            self._on_ignite()
        if mode == "webhook" and self._lights_webhook:
            asyncio.create_task(self._safe_webhook())
        label = target.replace("-", " ").replace("_", " ").title()
        self._speak(f"{greeting(self._now())}. Booting {label}.")
        await self._post(room, receipts.ignition(target))
        self._enqueue(Command("boot", [target], f"boot {target}"), room)
        return target

    async def _safe_webhook(self) -> None:
        try:
            assert self._lights_webhook is not None
            await self._lights_webhook()
        except Exception as e:
            log.warning("ignition lights webhook failed: %s", type(e).__name__)
