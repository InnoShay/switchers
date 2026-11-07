"""Approvals (SPEC §12.10): short codes, TTL, owner-only resolution, HUD events."""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, Literal

from roomservice.bus import bus as default_bus
from roomservice.contracts.events import ApprovalClosedEvent, ApprovalOpenEvent, HudEvent

CODE_ALPHABET = "ACDEFGHJKMNPQRTUVWXY3479"
CODE_LEN = 4
RESOLUTION_RE = re.compile(
    r"^(?:@\S+\s+)?(ok|no|approve|yes|deny|reject)\s+([A-Z0-9]{4})$", re.IGNORECASE
)
_POSITIVE = {"ok", "approve", "yes"}

Result = Literal["ok", "no", "expired", "unknown"]


@dataclass
class Approval:
    code: str
    cmd: str  # display text, e.g. `commit "waitlist page v1"`
    room_id: str  # room that asked; the receipt is posted back there
    created_at: float  # epoch seconds
    expires_at: float  # epoch seconds
    status: Literal["open", "closed", "expired"] = "open"
    payload: Any = None  # opaque to this module (the pending Command, project, ...)
    by: str | None = None

    @property
    def expires_at_ms(self) -> int:
        return int(self.expires_at * 1000)


@dataclass
class Resolution:
    result: Result  # "unknown" = no open approval has that code
    code: str
    approval: Approval | None = None
    by: str | None = None


def parse_resolution(text: str) -> tuple[Literal["ok", "no"], str] | None:
    """Match the §12.10 reply regex. Returns (action, CODE) or None."""
    m = RESOLUTION_RE.match(text.strip())
    if not m:
        return None
    action = "ok" if m.group(1).lower() in _POSITIVE else "no"
    return action, m.group(2).upper()


class Approvals:
    def __init__(
        self,
        ttl_s: int = 300,
        publish: Callable[[HudEvent], None] | None = None,
        on_open: Callable[[Approval], None] | None = None,
        on_close: Callable[[Approval, Result], None] | None = None,
        clock: Callable[[], float] | None = None,
        rand: Callable[[str], str] = secrets.choice,
    ) -> None:
        self.ttl_s = ttl_s
        self._publish = publish or default_bus.publish
        self.on_open = on_open  # e.g. speak "Approval needed."
        self.on_close = on_close
        self._clock = clock or (lambda: time.time())  # late-bound so freezegun can control it
        self._rand = rand
        self._open: dict[str, Approval] = {}

    # -- creation -----------------------------------------------------------------------

    def _new_code(self) -> str:
        while True:
            code = "".join(self._rand(CODE_ALPHABET) for _ in range(CODE_LEN))
            if code not in self._open:
                return code

    def create(self, cmd: str, room_id: str, payload: Any = None) -> Approval:
        now = self._clock()
        ap = Approval(
            code=self._new_code(),
            cmd=cmd,
            room_id=room_id,
            created_at=now,
            expires_at=now + self.ttl_s,
            payload=payload,
        )
        self._open[ap.code] = ap
        self._publish(ApprovalOpenEvent(code=ap.code, cmd=cmd, expires_at=ap.expires_at_ms))
        if self.on_open:
            self.on_open(ap)
        return ap

    # -- queries ------------------------------------------------------------------------

    def open_approvals(self) -> list[Approval]:
        return list(self._open.values())

    def get(self, code: str) -> Approval | None:
        return self._open.get(code.upper())

    # -- closing ------------------------------------------------------------------------

    def _close(self, ap: Approval, result: Result, by: str | None) -> None:
        self._open.pop(ap.code, None)
        ap.status = "expired" if result == "expired" else "closed"
        ap.by = by
        if result in ("ok", "no", "expired"):
            self._publish(ApprovalClosedEvent(code=ap.code, result=result, by=by))
        if self.on_close:
            self.on_close(ap, result)

    def sweep(self) -> list[Approval]:
        """Expire every open approval past its TTL. Call periodically."""
        now = self._clock()
        gone = [a for a in self._open.values() if now >= a.expires_at]
        for ap in gone:
            self._close(ap, "expired", None)
        return gone

    def resolve(
        self,
        text: str,
        sender_id: str,
        sender_name: str,
        owner_ids: Collection[str],
        is_agent: bool = False,
    ) -> Resolution | None:
        """Resolve an approval from a chat message, in whatever room it arrived.

        Returns None when the message is not a resolution, or the sender is an agent or not
        a paired owner (silently ignored). Otherwise a Resolution: "ok" / "no" / "expired",
        or "unknown" when no open approval has that code.
        """
        parsed = parse_resolution(text)
        if parsed is None or is_agent or sender_id not in owner_ids:
            return None
        action, code = parsed
        ap = self._open.get(code)
        if ap is None:
            return Resolution("unknown", code)
        if self._clock() >= ap.expires_at:
            self._close(ap, "expired", None)
            return Resolution("expired", code, ap)
        self._close(ap, action, sender_name)
        return Resolution(action, code, ap, sender_name)


__all__ = [
    "CODE_ALPHABET",
    "RESOLUTION_RE",
    "Approval",
    "Approvals",
    "Resolution",
    "parse_resolution",
]
