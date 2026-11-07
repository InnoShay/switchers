"""Allowlists (SPEC §12.3, §17): app keys, URL patterns, script keys. Pure, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from roomservice.contracts.config import DeskConfig, ScriptDef

NOT_ALLOWED = "not on the allowlist"
URL_NOT_ALLOWED = "url not allowed (https or localhost only)"
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


@dataclass(frozen=True)
class Check:
    ok: bool
    reason: str = ""  # refusal reason; goes after the "—" in `⛔ refused · <raw> — <reason>`
    value: str = ""  # resolved value (app key, URL)


def _deny(reason: str = NOT_ALLOWED) -> Check:
    return Check(False, reason)


def url_allowed(url: str) -> bool:
    """https://* , http://localhost:* , http://127.0.0.1:* only. No userinfo tricks."""
    if not url or any(c.isspace() or ord(c) < 32 for c in url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port  # raises ValueError on a bad port
    except ValueError:
        return False
    if parts.username is not None or parts.password is not None or not host:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and host in _LOCAL_HOSTS


def check_app(key: str, cfg: DeskConfig) -> Check:
    """`open <app-key>` / `close <app-key>`: key must exist in cfg.apps."""
    return Check(True, value=key) if key in cfg.apps else _deny()


def check_url(arg: str, cfg: DeskConfig) -> Check:
    """`url <alias or URL>`: alias -> cfg.urls, then the URL pattern rule applies."""
    url = str(cfg.urls[arg]) if arg in cfg.urls else arg
    if url_allowed(url):
        return Check(True, value=url)
    return _deny(URL_NOT_ALLOWED if ":" in arg else NOT_ALLOWED)


def resolve_project_url(entry: str, cfg: DeskConfig) -> Check:
    """A project's `urls` entry: alias key or http(s) URL."""
    return check_url(entry, cfg)


def check_script(key: str, cfg: DeskConfig) -> tuple[Check, ScriptDef | None]:
    """`run <script-key>`: returns the Check and the ScriptDef (its `confirm` drives approval)."""
    script = cfg.scripts.get(key)
    if script is None:
        return _deny(), None
    return Check(True, value=key), script
