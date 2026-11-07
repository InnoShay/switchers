"""Relay (SPEC §13): mirror mission-room events to every HQ room, and relay builder permission
requests as owner approvals. Pure logic: the desk injects post/upload/reply callables."""

from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from roomservice.agents.base import resolve_agent_key
from roomservice.bus import Bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Settings
from roomservice.contracts.events import SystemEvent
from roomservice.contracts.switch import MessagePayload
from roomservice.desk.approvals import Approval, Approvals
from roomservice.log import get_logger

log = get_logger("relay")

MAX_LINES = 6  # §13.4: every HQ message <= 6 lines
PLAN_BODY_LINES = MAX_LINES - 1  # header line + 5 body lines
RATE_LIMIT = 6  # mirrors / minute / mission
WINDOW_S = 60.0
SUMMARY_MAX = 100
GLOBAL_MAX = 30  # RS-10 safety valve: mirrors / 60 s across all missions, then stop

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


# -- RS-10: loop guards -----------------------------------------------------------------------

AUTO_REPLY_MARKERS = ("com.switch.auto_reply", "com.switch.admin")
OFFLINE_RE = re.compile(r"I'm currently offline", re.IGNORECASE)
_MENTION_AT_RE = re.compile(r"@(?=[\w-])")


def is_machine_message(msg: MessagePayload, raw: dict | None = None) -> bool:
    """Switch auto-reply/admin voice or any desk-* agent: never a command, never mirrored.

    The marker may sit in the payload dict (`raw`); the body prefix and the sender name are the
    fallbacks. Our own relay output never reaches this check (self-messages are dropped first).
    """
    if raw and any(raw.get(k) for k in AUTO_REPLY_MARKERS):
        return True
    if OFFLINE_RE.search(msg.body[:120]):
        return True
    return msg.sender_name.casefold().startswith("desk-")


def neutralise(text: str) -> str:
    """Full-width `＠` for every mention so a mirror can never address an agent."""
    return _MENTION_AT_RE.sub("＠", text)


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
        bus: Bus | None = None,
    ) -> None:
        self.settings = settings
        self.approvals = approvals
        self._hq_rooms = hq_rooms
        self._post = post
        self._upload = upload
        self._reply = reply
        self._clock = clock or (lambda: time.time())  # late-bound so freezegun works
        self._state: dict[str, _MissionState] = {}
        self._bus = bus
        self._all_sent: deque[float] = deque()  # every mirror, all missions (safety valve)
        self._tripped_at: float | None = None

    # -- inbound from the mission room -------------------------------------------------------

    def wants(self, room: RoomInfo, msg: MessagePayload) -> bool:
        """Should the desk receive this (unaddressed) message? Any mission-room chatter."""
        return room.kind == RoomKind.MISSION

    async def observe(
        self,
        room: RoomInfo,
        msg: MessagePayload,
        *,
        is_owner: bool = False,
        raw: dict | None = None,
    ) -> None:
        """Apply the §13.2 rules to a message someone else posted in a mission room."""
        if room.kind != RoomKind.MISSION or is_owner:  # never mirror what started in HQ
            return
        if is_machine_message(msg, raw):  # RS-10: auto-replies and desk-* chatter
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
        text = neutralise(text) if text else text
        caption = neutralise(caption)
        for hq in self._hq_rooms():
            if hq.kind != RoomKind.HQ:  # defensive: only HQ rooms are mirror targets
                continue
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
        if self._valve_open(now):
            return
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
        self._all_sent.append(now)
        await self._send_hq(text, png, filename, clip(caption))

    def _valve_open(self, now: float) -> bool:
        """RS-10 safety valve: True while mirroring is stopped (> GLOBAL_MAX mirrors in 60 s)."""
        if self._tripped_at is not None:
            if now - self._tripped_at < WINDOW_S:
                return True
            self._tripped_at = None
            self._all_sent.clear()
        while self._all_sent and now - self._all_sent[0] >= WINDOW_S:
            self._all_sent.popleft()
        if len(self._all_sent) > GLOBAL_MAX:
            self._tripped_at = now
            text = f"relay stopped: {len(self._all_sent)} mirrors in {int(WINDOW_S)}s (loop?)"
            log.warning(text)
            if self._bus is not None:
                self._bus.publish(SystemEvent(level="warn", text=text))
            return True
        return False

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
