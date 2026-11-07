"""Mission state, wrap, resume (SPEC §12.8). No network; git lookups are injectable."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from roomservice import store

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
ACTIVE_FILE = "active.json"

GitInfoFn = Callable[[Path], dict[str, Any]]
NowFn = Callable[[], datetime]


class NoActiveMission(Exception):
    """`wrap` with no mission in progress."""


def default_git_info(path: Path) -> dict[str, Any]:
    """{"branch","head","dirty_files"} via the git CLI; empty values if not a repo."""

    def git(*args: str) -> str | None:
        try:
            r = subprocess.run(
                ["git", "-C", str(path), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    head = git("rev-parse", "--short", "HEAD")
    status = git("status", "--porcelain")
    dirty = len([ln for ln in status.splitlines() if ln.strip()]) if status else 0
    return {"branch": branch, "head": head, "dirty_files": dirty}


def _now() -> datetime:
    return datetime.now().astimezone()


def _tilde(path: str | Path | None) -> str | None:
    """Show the home directory as `~` (the §12.8 example shape)."""
    if path is None:
        return None
    s = str(path)
    home = str(Path.home())
    return "~" + s[len(home) :] if s == home or s.startswith(home + "/") else s


def _add_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


@dataclass
class MissionState:
    slug: str
    project: str | None
    started_at: float  # epoch seconds
    path: str | None = None
    title: str | None = None
    screenshot_url: str | None = None
    apps: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    terminals: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "project": self.project,
            "started_at": self.started_at,
            "path": self.path,
            "title": self.title,
            "screenshot_url": self.screenshot_url,
            "opened": {"apps": self.apps, "urls": self.urls, "terminals": self.terminals},
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> MissionState:
        opened = d.get("opened") or {}
        return cls(
            slug=d["slug"],
            project=d.get("project"),
            started_at=float(d["started_at"]),
            path=d.get("path"),
            title=d.get("title"),
            screenshot_url=d.get("screenshot_url"),
            apps=list(opened.get("apps", [])),
            urls=list(opened.get("urls", [])),
            terminals=list(opened.get("terminals", [])),
        )


class StateManager:
    """Active mission (memory + active.json), wrap files, booted-project tracking."""

    def __init__(self, git_info: GitInfoFn = default_git_info, now: NowFn = _now) -> None:
        self._git_info = git_info
        self._now = now
        self.active: MissionState | None = None
        # A project counts as booted for the life of the process until `close all` or `wrap`.
        self.booted: set[str] = set()
        self._load_active()

    # -- files --------------------------------------------------------------------------

    @staticmethod
    def active_path() -> Path:
        return store.state_dir() / ACTIVE_FILE

    @staticmethod
    def state_path(slug: str) -> Path:
        if not SLUG_RE.match(slug):
            raise ValueError(f"invalid mission slug: {slug!r}")
        return store.state_dir() / f"{slug}.json"

    def _load_active(self) -> None:
        d = store.read_json(self.active_path(), None)
        if isinstance(d, dict):
            try:
                self.active = MissionState.from_json(d)
            except (KeyError, TypeError, ValueError):
                self.active = None

    def _save_active(self) -> None:
        if self.active is None:
            self.active_path().unlink(missing_ok=True)
        else:
            store.write_json(self.active_path(), self.active.to_json())

    # -- booted tracking ----------------------------------------------------------------

    def mark_booted(self, project: str) -> None:
        self.booted.add(project)

    def is_booted(self, project: str) -> bool:
        return project in self.booted

    def forget_booted(self, project: str | None = None) -> None:
        """`close all` (or `wrap`) ends the booted state; one project or all of them."""
        if project is None:
            self.booted.clear()
        else:
            self.booted.discard(project)

    # -- mission lifecycle --------------------------------------------------------------

    def start_mission(
        self,
        slug: str,
        project: str | None,
        path: Path | str | None = None,
        screenshot_url: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        """Begin a mission. An already-active mission is auto-wrapped silently first
        (state file only). Returns the auto-wrapped state, or None."""
        self.state_path(slug)  # validates the slug, raises ValueError
        auto = self._wrap_active(keep_booted=True) if self.active else None
        self.active = MissionState(
            slug=slug,
            project=project,
            started_at=self._now().timestamp(),
            path=_tilde(path),
            title=title,
            screenshot_url=screenshot_url,
        )
        self._save_active()
        return auto

    def record_opened(self, kind: str, value: str) -> None:
        """Record an opened `apps` / `urls` / `terminals` entry in the active mission."""
        if self.active is None:
            return
        if kind not in ("apps", "urls", "terminals"):
            raise ValueError(f"unknown opened kind: {kind!r}")
        _add_unique(getattr(self.active, kind), value)
        self._save_active()

    def wrap(self) -> dict[str, Any]:
        """Write `<slug>.json`, clear the active mission and booted projects; return the JSON."""
        if self.active is None:
            raise NoActiveMission("no active mission")
        return self._wrap_active(keep_booted=False)

    def _wrap_active(self, keep_booted: bool) -> dict[str, Any]:
        m = self.active
        assert m is not None
        wrapped = self._now()
        git = None
        if m.path:
            git = self._git_info(Path(m.path).expanduser())
        state: dict[str, Any] = {
            "slug": m.slug,
            "project": m.project,
            "wrapped_at": wrapped.isoformat(timespec="seconds"),
            "mission_minutes": max(0, round((wrapped.timestamp() - m.started_at) / 60)),
            "path": m.path,
            "git": {
                "branch": (git or {}).get("branch"),
                "head": (git or {}).get("head"),
                "dirty_files": (git or {}).get("dirty_files", 0),
            }
            if git is not None
            else None,
            "opened": {"apps": list(m.apps), "urls": list(m.urls), "terminals": list(m.terminals)},
            "screenshot_url": m.screenshot_url,
        }
        store.write_json(self.state_path(m.slug), state)
        self.active = None
        self._save_active()
        if not keep_booted:
            self.booted.clear()
        return state

    # -- resume -------------------------------------------------------------------------

    def latest_state(self, project: str) -> dict[str, Any] | None:
        """Newest (by wrapped_at) saved state whose project matches."""
        best: tuple[float, dict[str, Any]] | None = None
        for f in store.state_dir().glob("*.json"):
            if f.name == ACTIVE_FILE:
                continue
            d = store.read_json(f, None)
            if not isinstance(d, dict) or d.get("project") != project:
                continue
            try:
                ts = datetime.fromisoformat(d["wrapped_at"]).timestamp()
            except (KeyError, TypeError, ValueError):
                ts = f.stat().st_mtime
            if best is None or ts > best[0]:
                best = (ts, d)
        return best[1] if best else None

    def resume_extra_urls(self, saved: dict[str, Any], already_opened: list[str]) -> list[str]:
        """Saved `opened.urls` that are not already open (they come after the boot's own)."""
        urls = (saved.get("opened") or {}).get("urls", [])
        return [u for u in urls if u not in already_opened]
