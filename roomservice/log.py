"""Logging (SPEC §19): rich console + JSON lines at ~/.roomservice/logs/runtime.jsonl.

Never logs message bodies longer than 400 chars or any key; redacts Authorization,
api_key and token values.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from rich.logging import RichHandler

from roomservice.store import logs_dir

MAX_MSG = 400
_REDACTED = "[REDACTED]"

# Order matters: header-style first, then key/value pairs, then bare bearer tokens.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*)(bearer\s+)?[^\s,;'\"}]+"), r"\1" + _REDACTED),
    (
        re.compile(
            r"(?i)((?:api[_-]?key|token|secret|password)['\"]?\s*[:=]\s*['\"]?)[^\s,;'\"}]+"
        ),
        r"\1" + _REDACTED,
    ),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1" + _REDACTED),
]


def redact(text: str) -> str:
    """Mask Authorization headers, api_key / token / secret values and bearer tokens."""
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def clip(text: str, limit: int = MAX_MSG) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class _Safe(logging.Filter):
    """Redact secrets and clip long messages before any handler sees the record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = clip(redact(record.getMessage()))
        record.args = None
        return True


class _JsonLines(logging.Handler):
    def __init__(self, path) -> None:
        super().__init__()
        self._path = path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = {
                "ts": datetime.fromtimestamp(record.created, UTC).isoformat(
                    timespec="milliseconds"
                ),
                "level": record.levelname.lower(),
                "agent": getattr(record, "agent", None),
                "room": getattr(record, "room", None),
                "event": getattr(record, "event", None),
                "msg": record.msg,
            }
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception:  # logging must never crash the runtime
            self.handleError(record)


_configured = False


def setup_logging(level: int = logging.INFO, console: bool = True) -> logging.Logger:
    """Configure the 'roomservice' logger once. Safe to call repeatedly."""
    global _configured
    logger = logging.getLogger("roomservice")
    if _configured:
        return logger
    logger.setLevel(level)
    logger.propagate = False
    # Filters on a logger do not see child-logger records, so attach to the handlers.
    handlers: list[logging.Handler] = [_JsonLines(logs_dir() / "runtime.jsonl")]
    if console:
        handlers.append(RichHandler(show_path=False, markup=False, rich_tracebacks=False))
    for h in handlers:
        h.addFilter(_Safe())
        logger.addHandler(h)
    # httpx logs full URLs at INFO; keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _configured = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Child logger of 'roomservice'. Pass extra={'agent':…, 'room':…, 'event':…} for fields."""
    return logging.getLogger("roomservice" + (f".{name}" if name else ""))


def reset_logging() -> None:
    """Test helper: drop handlers so setup_logging can run again."""
    global _configured
    logger = logging.getLogger("roomservice")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    _configured = False
