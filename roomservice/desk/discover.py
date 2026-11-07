"""Dynamic project discovery (RS-07): open any directory under the projects root(s).

No desk.yaml entry is needed: `resolve_project(name)` looks at the directories under
`ROOMSERVICE_PROJECTS_DIR` (comma list, default `~/cooks`) at request time and `detect()` works
out how to run what it finds. Pure helpers plus one small async dev-server launcher; every
subprocess is an argv list, never a shell.
"""

from __future__ import annotations

import asyncio
import contextlib
import difflib
import json
import os
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from roomservice.contracts.config import DeskConfig, Project, Terminal
from roomservice.log import get_logger

log = get_logger("desk.discover")

ENV_VAR = "ROOMSERVICE_PROJECTS_DIR"
DEFAULT_ROOT = "~/cooks"
FUZZY_MIN = 0.75
MIN_WORD = 4
LIST_MAX = 20
DEV_URL_TIMEOUT_S = 45
COMMON_PORTS = (5173, 3000, 8080)
_SKIP = {"node_modules"}
_URL_RE = re.compile(r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]):(\d{2,5})")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# -- roots and directories --------------------------------------------------------------


def roots() -> list[Path]:
    raw = os.environ.get(ENV_VAR) or DEFAULT_ROOT
    return [Path(p.strip()).expanduser() for p in raw.split(",") if p.strip()]


def root_label() -> str:
    home = str(Path.home())
    return ", ".join(str(r).replace(home, "~", 1) for r in roots())


def first_root() -> Path | None:
    return next((r for r in roots() if r.is_dir()), None)


def list_dirs() -> list[Path]:
    """Visible, non-node_modules directories directly under each root (read fresh every call)."""
    out: list[Path] = []
    for r in roots():
        try:
            entries = sorted(r.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for p in entries:
            if p.name.startswith(".") or p.name in _SKIP:
                continue
            try:
                if p.is_dir():
                    out.append(p)
            except OSError:
                continue
    return out


# -- name matching ----------------------------------------------------------------------


@dataclass
class Match:
    name: str
    path: Path


@dataclass
class Ambiguous:
    candidates: list[str]

    @property
    def text(self) -> str:
        return "❓ which one? " + ", ".join(self.candidates)


def _squash(s: str) -> str:
    return re.sub(r"[\s_\-]+", "", s.casefold())


def find(name: str, dirs: list[Path] | None = None) -> Match | Ambiguous | None:
    """exact (case-insensitive) -> prefix -> substring -> fuzzy (ratio >= 0.75)."""
    dirs = list_dirs() if dirs is None else dirs
    q = name.strip().casefold()
    if not q:
        return None
    qs = _squash(q)
    tiers = (
        lambda d: d.name.casefold() == q or _squash(d.name) == qs,
        lambda d: d.name.casefold().startswith(q),
        lambda d: q in d.name.casefold(),
    )
    for test in tiers:
        hits = [d for d in dirs if test(d)]
        if len(hits) == 1:
            return Match(hits[0].name, hits[0])
        if hits:
            return Ambiguous(sorted({d.name for d in hits}))
    scored = sorted(
        ((difflib.SequenceMatcher(None, q, d.name.casefold()).ratio(), d) for d in dirs),
        key=lambda t: -t[0],
    )
    good = [(r, d) for r, d in scored if r >= FUZZY_MIN]
    if not good:
        return None
    if len(good) > 1 and good[0][0] - good[1][0] < 0.05:
        return Ambiguous(sorted({d.name for _, d in good}))
    return Match(good[0][1].name, good[0][1])


# -- detection --------------------------------------------------------------------------


@dataclass
class Detected:
    name: str
    path: Path
    kind: str  # node | python | xcode | rust | go | plain | configured
    project: Project
    dev_argv: list[str] | None = None  # long-running dev command (run through the desk)
    install_argv: list[str] | None = None  # run first (only set when deps are missing)
    xcode: Path | None = None  # .xcworkspace / .xcodeproj to open instead of the editor
    notes: list[str] = field(default_factory=list)


def _pm(path: Path) -> str:
    if (path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (path / "yarn.lock").exists():
        return "yarn"
    if (path / "bun.lockb").exists() or (path / "bun.lock").exists():
        return "bun"
    return "npm"


def _read(path: Path, limit: int = 20000) -> str:
    try:
        return path.read_text(errors="replace")[:limit]
    except OSError:
        return ""


def _detect_node(path: Path) -> tuple[list[str], list[str] | None] | None:
    pkg = path / "package.json"
    if not pkg.is_file():
        return None
    try:
        scripts = (json.loads(pkg.read_text()) or {}).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return None
    script = "dev" if "dev" in scripts else "start" if "start" in scripts else None
    if script is None:
        return None
    pm = _pm(path)
    install = [pm, "install"] if not (path / "node_modules").exists() else None
    return [pm, "run", script], install


def _detect_python(path: Path) -> list[str] | None:
    uv = (path / "uv.lock").exists() or (path / "pyproject.toml").exists()
    py = ["uv", "run", "python"] if uv else ["python3"]
    if (path / "manage.py").is_file():
        return [*py, "manage.py", "runserver"]
    for fname in ("main.py", "app.py"):
        f = path / fname
        if not f.is_file():
            continue
        text = _read(f)
        if "FastAPI(" in text:
            return ["uv", "run", "uvicorn", f"{fname[:-3]}:app", "--reload"]
        if "Flask(" in text or "__main__" in text:
            return [*py, fname]
    return None


def _xcode(path: Path) -> Path | None:
    for pat in ("*.xcworkspace", "*.xcodeproj"):
        for p in sorted(path.glob(pat)):
            if p.name != "Pods.xcworkspace":
                return p
    return None


def detect(name: str, path: Path) -> Detected:
    """Work out how to open/run `path`. Never raises on odd contents."""
    kind: str = "plain"
    dev: list[str] | None = None
    install: list[str] | None = None
    xc: Path | None = None
    try:
        if node := _detect_node(path):
            kind = "node"
            dev, install = node
        elif any(
            (path / f).is_file() for f in ("pyproject.toml", "manage.py", "app.py", "main.py")
        ):
            kind = "python"
            dev = _detect_python(path)
        elif xc := _xcode(path):
            kind = "xcode"
        elif (path / "Cargo.toml").is_file():
            kind = "rust"
        elif (path / "go.mod").is_file():
            kind = "go"
    except OSError as e:
        log.warning("detect %s failed: %s", path, e)
    terminals = [Terminal(name="dev", cmd=" ".join(dev))] if dev else []
    project = Project(
        keywords=[name],
        path=path,
        open_editor=xc is None,
        terminals=terminals,
        urls=[],
        focus=True,
        music=None,
        lights=False,
    )
    log.info("detected %s: kind=%s dev=%s install=%s xcode=%s", name, kind, dev, install, xc)
    return Detected(name, path, kind, project, dev, install, xc)


# -- resolution -------------------------------------------------------------------------


@dataclass
class Resolved:
    name: str
    detected: Detected

    @property
    def project(self) -> Project:
        return self.detected.project


@dataclass
class NotFound:
    name: str
    root: str

    @property
    def text(self) -> str:
        return f"⛔ refused · no project called {self.name} in {self.root}"


def resolve_project(name: str, cfg: DeskConfig | None = None) -> Resolved | Ambiguous | NotFound:
    """desk.yaml first (unchanged: no detection), else the directories on disk."""
    if cfg is not None and name in cfg.projects:
        p = cfg.projects[name]
        return Resolved(name, Detected(name, p.path, "configured", p))
    hit = find(name)
    if isinstance(hit, Match):
        return Resolved(hit.name, detect(hit.name, hit.path))
    if isinstance(hit, Ambiguous):
        return hit
    return NotFound(name, root_label())


def ignition_target(body: str, skip_words: set[str] | None = None) -> str | None:
    """A word (>= 4 chars, exact case-insensitive) of `body` equal to a directory name."""
    skip = {w.casefold() for w in (skip_words or set())}
    dirs = {d.name.casefold(): d.name for d in list_dirs() if len(d.name) >= MIN_WORD}
    for word in re.findall(r"[\w-]+", body.casefold()):
        if len(word) >= MIN_WORD and word in dirs and word not in skip:
            return dirs[word]
    return None


def projects_text(cfg: DeskConfig) -> str:
    """`projects` verb: configured then discovered names (max 20)."""
    names = list(cfg.projects)
    seen = {n.casefold() for n in names}
    for d in list_dirs():
        if d.name.casefold() not in seen:
            names.append(d.name)
            seen.add(d.name.casefold())
    if not names:
        return f"no projects found in {root_label()}"
    more = f" (+{len(names) - LIST_MAX} more)" if len(names) > LIST_MAX else ""
    return f"{len(names)} in {root_label()}: " + ", ".join(names[:LIST_MAX]) + more


# -- dev server launcher ----------------------------------------------------------------


def parse_dev_url(line: str) -> str | None:
    m = _URL_RE.search(_ANSI_RE.sub("", line))
    return f"http://localhost:{m.group(1)}" if m else None


async def _drain(proc: asyncio.subprocess.Process) -> None:
    assert proc.stdout is not None
    with contextlib.suppress(Exception):
        while await proc.stdout.readline():
            pass


def kill_group(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()


async def launch_dev_server(
    argv: list[str], cwd: Path, timeout_s: float = DEV_URL_TIMEOUT_S
) -> tuple[str | None, asyncio.subprocess.Process | None]:
    """Start `argv` in the background and return its first localhost URL and the process.

    On timeout, early exit or failure to start the process is killed and (None, None) comes
    back so the caller can fall back to a visible terminal.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as e:
        log.warning("dev server start failed: %s", e)
        return None, None
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout_s
    url: str | None = None
    while url is None:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), left)
        except TimeoutError:
            break
        if not line:
            break
        url = parse_dev_url(line.decode("utf-8", "replace"))
    if url is None:
        kill_group(proc)
        return None, None
    asyncio.create_task(_drain(proc))
    return url, proc
