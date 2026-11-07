"""Receipt formats (SPEC §12.11). Pure string functions, snapshot-tested."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def fmt_seconds(seconds: float) -> str:
    """Seconds with one decimal: 3.44 -> '3.4s'."""
    return f"{seconds:.1f}s"


def fmt_cmd(verb: str, args: list[str] | tuple[str, ...] = ()) -> str:
    """`<verb> <args>`; an arg containing whitespace or quotes is shown in double quotes."""
    parts = [verb]
    for a in args:
        needs_quotes = a == "" or any(c.isspace() or c in "\"'" for c in a)
        parts.append('"' + a.replace('"', '\\"') + '"' if needs_quotes else a)
    return " ".join(parts)


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def ok(verb: str, args: list[str], summary: str, seconds: float) -> str:
    """✅ <verb> <args> · <summary> · <s>s"""
    return _join("✅ " + fmt_cmd(verb, args), summary, fmt_seconds(seconds))


def queued(raw: str, current_raw: str) -> str:
    return f"⏳ queued · {raw} (busy with {current_raw})"


def refused(raw: str, reason: str) -> str:
    return f"⛔ refused · {raw} — {reason}"


def refused_rate_limit(limit: int = 20) -> str:
    return f"⛔ refused · rate limit ({limit}/min)"


def refused_frozen() -> str:
    return "⛔ refused · frozen by owner"


def refused_too_many(limit: int = 5) -> str:
    return f"⛔ refused · more than {limit} commands in one message"


def didnt_understand(line: str) -> str:
    return f'⛔ didn\'t understand · "{line}" · try: @hands help'


def approval_needed(cmd: str, project: str | None, code: str, ttl_s: int = 300) -> str:
    """Two lines; the second has two spaces around `ok CODE  or  no CODE`."""
    where = f" in {project}" if project else ""
    minutes = max(1, math.ceil(ttl_s / 60))
    return (
        f"⚠️ approval needed · {cmd}{where}\nOwner: reply  ok {code}  or  no {code}  ({minutes} min)"
    )


def approved(name: str, summary: str, seconds: float) -> str:
    return _join(f"✅ approved by {name}", summary, fmt_seconds(seconds))


def declined(name: str, cmd: str) -> str:
    return f"🚫 declined by {name} · {cmd}"


def expired(code: str, cmd: str) -> str:
    return f"⌛ expired · {code} · {cmd}"


def hhmm_ist(when: datetime) -> str:
    """HH:MM in IST. A naive datetime is taken to already be IST."""
    if when.tzinfo is not None:
        when = when.astimezone(IST)
    return when.strftime("%H:%M")


def screenshot_caption(label: str, url: str | None, when: datetime) -> str:
    """📸 <project|screen> · <url or "screen"> · <HH:MM> IST"""
    return f"📸 {label} · {url or 'screen'} · {hhmm_ist(when)} IST"


def ignition(target: str) -> str:
    return f"⚡ ignition · booting {target}"


def hands_now_on(agent_name: str) -> str:
    return f"🫱 hands is now on {agent_name}"


def paired(sender_name: str, room_name: str) -> str:
    return f"🔐 paired · {sender_name} on {room_name}"


def frozen(name: str) -> str:
    return f"🧊 frozen by {name}"


def unfrozen(name: str) -> str:
    return f"🔥 unfrozen by {name}"


# -- verb-specific receipts quoted in §12.5, §12.8, §12.9 -------------------------------


def wrap(slug: str, minutes: int, state: dict[str, Any]) -> str:
    """✅ wrap · <slug> · <n> min, then the state JSON (compact) in a fenced block."""
    body = json.dumps(state, separators=(",", ":"), ensure_ascii=False)
    return f"✅ wrap · {slug} · {minutes} min\n```json\n{body}\n```"


def resume(project: str, summary: str, head: str | None = None, no_state: bool = False) -> str:
    """✅ resume volt · editor, 1 terminal, 2 tabs · last head 3f2a91c  (or `· no saved state`)."""
    tail = "no saved state" if no_state else (f"last head {head}" if head else "")
    return _join(f"✅ resume {project}", summary, tail)


def mission_already_booted(slug: str) -> str:
    return f"✅ mission {slug} · already booted · hands assumed"
