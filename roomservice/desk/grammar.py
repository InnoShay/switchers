"""Command grammar (SPEC §12.2): chat body -> Command / ParseError. Pure, no I/O."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

MENTION_RE = re.compile(r"^@(?:hands|desk-laptop|desk-backup)[,:]?\s+(?P<cmd>.+)$", re.IGNORECASE)
_MENTION_TOKEN_RE = re.compile(r"@\S+")

ALIASES: dict[str, str] = {
    "screenshot": "shot",
    "show": "shot",
    "snap": "shot",
    "show-me": "shot",
    "speak": "say",
    "start": "boot",
    "goodnight": "wrap",
    "stop": "freeze",
    "halt": "freeze",
    "approve": "ok",
    "yes": "ok",
    "deny": "no",
    "reject": "no",
}

# Canonical verbs of SPEC §12.3.
VERBS: frozenset[str] = frozenset(
    {
        "boot",
        "mission",
        "open",
        "url",
        "run",
        "focus",
        "shot",
        "say",
        "close",
        "commit",
        "push",
        "wrap",
        "resume",
        "status",
        "lights",
        "release",
        "pair",
        "ok",
        "no",
        "freeze",
        "unfreeze",
        "help",
    }
)

DEFAULT_MAX_COMMANDS = 5


def too_many_commands_text(limit: int = DEFAULT_MAX_COMMANDS) -> str:
    """Exact refusal text for a message with more than `limit` commands (SPEC §12.2)."""
    return f"⛔ refused · more than {limit} commands in one message"


@dataclass(frozen=True)
class Command:
    verb: str
    args: list[str]
    raw: str


@dataclass(frozen=True)
class ParseError:
    raw: str
    reason: str


@dataclass
class ParsedMessage:
    """Result of parsing a whole chat message."""

    items: list[Command | ParseError] = field(default_factory=list)
    refusal: str | None = None  # set when extra commands were dropped (> max)

    @property
    def commands(self) -> list[Command]:
        return [i for i in self.items if isinstance(i, Command)]


def parse_command(text: str) -> Command | ParseError:
    """Tokenize one command string (posix shlex), alias-map the verb."""
    raw = text.strip()
    if not raw:
        return ParseError(raw, "empty command")
    try:
        tokens = shlex.split(raw, posix=True)
    except ValueError as e:  # unbalanced quotes / trailing escape
        return ParseError(raw, f"unbalanced quotes ({e})")
    if not tokens:
        return ParseError(raw, "empty command")
    first = tokens[0].lower()
    verb = ALIASES.get(first, first)
    args = tokens[1:]
    if first == "show" and args and args[0].lower() == "me":
        args = args[1:]  # "show me" -> shot
    if verb not in VERBS:
        return ParseError(raw, f"unknown verb '{first}'")
    return Command(verb=verb, args=args, raw=raw)


def command_lines(body: str, addressed: bool) -> list[str]:
    """Command strings found in `body` (mention lines, else the addressed fallback)."""
    found: list[str] = []
    for line in body.splitlines():
        m = MENTION_RE.match(line.strip())
        if m:
            found.append(m.group("cmd").strip())
    if found or not addressed:
        return found
    # Addressed with no matching line: whole body minus every @token is one command.
    # RS-07: only when its first word is a known verb or alias; anything else is prose.
    fallback = " ".join(_MENTION_TOKEN_RE.sub(" ", body).split())
    first = fallback.split(" ", 1)[0].lower()
    if ALIASES.get(first, first) in VERBS:
        return [fallback]
    return []


def parse_message(
    body: str, addressed: bool = False, max_commands: int = DEFAULT_MAX_COMMANDS
) -> ParsedMessage:
    """Parse a chat message into at most `max_commands` items.

    Extra commands are dropped and `refusal` carries the exact §12.2 text.
    Prose (no mention line, no leading verb) yields nothing: ignored silently.
    """
    cmds = command_lines(body, addressed)
    out = ParsedMessage()
    if not cmds:
        return out
    if len(cmds) > max_commands:
        out.refusal = too_many_commands_text(max_commands)
        cmds = cmds[:max_commands]
    out.items = [parse_command(c) for c in cmds]
    return out
