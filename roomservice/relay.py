"""Relay (SPEC §13): mirror mission-room events to every HQ room, and relay builder permission
requests as owner approvals. Pure logic: the desk injects post/upload/reply callables."""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from roomservice.agents.base import resolve_agent_key
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Settings
from roomservice.contracts.switch import MessagePayload
from roomservice.desk.approvals import Approval, Approvals
from roomservice.log import get_logger

log = get_logger("relay")

MAX_LINES = 6  # §13.4: every HQ message <= 6 lines
PLAN_BODY_LINES = MAX_LINES - 1  # header line + 5 body lines
RATE_LIMIT = 6  # mirrors / minute / mission
WINDOW_S = 60.0
SUMMARY_MAX = 100

# -- detectors (easy to swap once tests/fixtures/permission_request.json exists, S5) -----------

PERMISSION_RE = re.compile(r"Allow once|Allow for this session")
DONE_RE = re.compile(r"\b(?:done|finished)\b", re.IGNORECASE)
KICKOFF_RE = re.compile(r"@(?:desk\S*|hands)\b[^\n]*\bmission\s+\S+", re.IGNORECASE)
WRAP_RE = re.compile(r"^✅ wrap · \S+ · (\d+) min")


def is_permission_request(body: str) -> bool:
    return PERMISSION_RE.search(body) is not None


def permission_summary(body: str) -> str:
    """One line describing what the builder wants (first line that is not the Allow prompt)."""
    for raw in body.splitlines():
        line = re.sub(r"[`*_]", "", raw).strip()
        if line and not PERMISSION_RE.search(line):
            return line[:SUMMARY_MAX]
    return "permission request"


# -- text helpers -------------------------------------------------------------------------


def _lines(text: str) -> list[str]:
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


def clip(text: str, max_lines: int = MAX_LINES) -> str:
    return "\n".join(text.splitlines()[:max_lines])


def first_line(text: str) -> str:
    ls = _lines(text)
    return ls[0].strip() if ls else ""


@dataclass
class BuilderAsk:
    """Approval payload: where to say `yes` / `no` (thread_id, else the request's message_id)."""

    room: RoomInfo
    thread_id: str


@dataclass
class _MissionState:
    sent: deque[float] = field(default_factory=deque)
    suppressed: int = 0
    suppressed_since: float = 0.0
    last_collapse: float = -1e18
    planned: bool = False


class Relay:
    def __init__(
        self,
        *,
        settings: Settings,
        approvals: Approvals,
        hq_rooms: Callable[[], list[RoomInfo]],
        post: Callable[[str, str], Awaitable[object]],
        upload: Callable[[str, bytes, str, str], Awaitable[object]],
        reply: Callable[[RoomInfo, str, str | None], Awaitable[None]],
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings
        self.approvals = approvals
        self._hq_rooms = hq_rooms
        self._post = post
        self._upload = upload
        self._reply = reply
        self._clock = clock or (lambda: time.time())  # late-bound so freezegun works
        self._state: dict[str, _MissionState] = {}

    # -- inbound from the mission room -------------------------------------------------------

    def wants(self, room: RoomInfo, msg: MessagePayload) -> bool:
        """Should the desk receive this (unaddressed) message? Any mission-room chatter."""
        return room.kind == RoomKind.MISSION

    async def observe(self, room: RoomInfo, msg: MessagePayload, *, is_owner: bool = False) -> None:
        """Apply the §13.2 rules to a message someone else posted in a mission room."""
        if room.kind != RoomKind.MISSION or is_owner:
            return
        try:
            await self._observe(room, msg)
        except Exception as e:  # relay must never break the desk
            log.warning("relay failed in %s: %s", room.name, e)

    async def _observe(self, room: RoomInfo, msg: MessagePayload) -> None:
        key = resolve_agent_key(msg.sender_name, msg.sender)
        body = msg.body
        st = self._st(room)
        if key == "concierge":
            if st.planned or KICKOFF_RE.search(body):
                return
            st.planned = True
            lines = _lines(body)[:PLAN_BODY_LINES]
            await self._mirror(room, "\n".join([f"🧭 plan · {room.name}", *lines]))
        elif key == "builder" or "switch" in msg.sender_name.casefold():
            if is_permission_request(body):
                await self._builder_ask(room, msg)
            elif key == "builder" and DONE_RE.search(body):
                await self._mirror(room, f"🛠️ builder · {first_line(body)[:200]}")

    # -- the desk's own posts in a mission room (the base class drops self-messages) ---------

    async def on_desk_post(self, room: RoomInfo, text: str) -> None:
        if room.kind != RoomKind.MISSION:
            return
        try:
            if text.startswith("⚠️ approval needed"):
                await self._mirror(room, clip(text))
            elif (m := WRAP_RE.match(text)) is not None:
                await self._mirror(room, f"🌙 wrapped · {room.name} · {m.group(1)} min")
        except Exception as e:
            log.warning("relay failed in %s: %s", room.name, e)

    async def on_desk_upload(self, room: RoomInfo, png: bytes, filename: str, caption: str) -> None:
        if room.kind != RoomKind.MISSION:
            return
        try:
            await self._mirror(room, None, png=png, filename=filename, caption=caption)
        except Exception as e:
            log.warning("relay upload failed in %s: %s", room.name, e)

    # -- builder approval relay (§13.3) ------------------------------------------------------

    async def _builder_ask(self, room: RoomInfo, msg: MessagePayload) -> None:
        summary = permission_summary(msg.body)
        if not self.settings.roomservice_relay_approvals:
            await self._mirror(room, f"⚠️ builder asks · {summary} — approve on the laptop")
            return
        ap = self.approvals.create(
            f"builder: {summary}",
            room.id,
            payload=BuilderAsk(room, msg.thread_id or msg.message_id),
        )
        await self._mirror(
            room,
            f"⚠️ builder asks · {summary}\nOwner: reply  ok {ap.code}  or  no {ap.code}",
        )

    async def answer(self, ap: Approval, approved: bool) -> None:
        """Owner decided: post exactly `yes` / `no` in the builder's thread."""
        ask = ap.payload
        if isinstance(ask, BuilderAsk):
            await self._reply(ask.room, "yes" if approved else "no", ask.thread_id)

    # -- mirroring + rate limit --------------------------------------------------------------

    def _st(self, room: RoomInfo) -> _MissionState:
        return self._state.setdefault(room.name, _MissionState())

    async def _send_hq(
        self, text: str | None, png: bytes | None = None, filename: str = "", caption: str = ""
    ) -> None:
        for hq in self._hq_rooms():
            try:
                if png is not None:
                    await self._upload(hq.id, png, filename, caption)
                else:
                    await self._post(hq.id, clip(text or ""))
            except Exception as e:
                log.warning("mirror to %s failed: %s", hq.name, e)

    async def _mirror(
        self,
        room: RoomInfo,
        text: str | None,
        *,
        png: bytes | None = None,
        filename: str = "shot.png",
        caption: str = "",
    ) -> None:
        now = self._clock()
        st = self._st(room)
        await self._flush(room.name, st, now)
        while st.sent and now - st.sent[0] >= WINDOW_S:
            st.sent.popleft()
        if len(st.sent) >= RATE_LIMIT:
            if st.suppressed == 0:
                st.suppressed_since = now
            st.suppressed += 1
            return
        st.sent.append(now)
        await self._send_hq(text, png, filename, clip(caption))

    async def _flush(self, name: str, st: _MissionState, now: float) -> None:
        if (
            st.suppressed
            and now - st.suppressed_since >= WINDOW_S
            and now - st.last_collapse >= WINDOW_S
        ):
            n, st.suppressed, st.last_collapse = st.suppressed, 0, now
            await self._send_hq(f"… +{n} updates in {name}")

    async def tick(self) -> None:
        """Emit due `… +N updates` summaries (call periodically; also runs on every mirror)."""
        now = self._clock()
        for name, st in list(self._state.items()):
            await self._flush(name, st, now)
