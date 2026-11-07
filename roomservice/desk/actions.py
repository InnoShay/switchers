"""Verb execution (SPEC §12.3, §12.5, §12.8). No chat I/O here: the DeskAgent posts receipts.

`DeskActions.execute()` returns an ActionResult; refusals/failures raise `Refuse` internally and
come back as `ok=False` with a one-line reason. Subprocesses go through the OS adapter with argv
lists only. git is never forced.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from roomservice import store
from roomservice.bus import bus as default_bus
from roomservice.contracts.agent import RoomInfo
from roomservice.contracts.config import DeskConfig, Project, Settings
from roomservice.contracts.events import (
    IgnitionEvent,
    MissionEvent,
    ScreenshotEvent,
    SpeakEvent,
    SystemEvent,
    now_ms,
)
from roomservice.contracts.os import OSAdapter, RunResult
from roomservice.desk import allowlist, discover, receipts
from roomservice.desk.execcmd import EXEC_MAX_CHARS, EXEC_TIMEOUT_S, ShellRunner
from roomservice.desk.grammar import Command
from roomservice.desk.state import SLUG_RE, NoActiveMission, StateManager
from roomservice.log import get_logger

log = get_logger("desk.actions")

SAY_MAX = 200
IGNITE_WINDOW_S = 60.0
WAIT_FOR_TIMEOUT_S = 45
GIT_TIMEOUT_S = 120

HELP_TEXT = "\n".join(
    [
        "@computer <verb> ... — one command per line, max 5",
        "boot <project> · resume <project> · task <name> <project|none> · wrap",
        "open <app> · close <app|all> · url <alias|https-url> · focus on|off",
        'shot [screen|page] · say "<text>" · lights on|off',
        'run <script> · commit "<msg>" · push   (asks for approval)',
        'exec "<command>" — any shell command, ALWAYS asks for approval (bash -lc, 120 s)',
        "projects — list the projects the desk can open (configured + folders under the root)",
        "status · help · release",
        "owner only: ok|no <CODE> · pause · unpause · pair <6 digits>",
    ]
)


class Refuse(Exception):
    """A command that must not (or cannot) run; the message is the one-line reason."""


class Reply(Refuse):
    """A refusal that carries its own full receipt text (RS-07: discovery answers)."""

    def __init__(self, reason: str, text: str) -> None:
        super().__init__(reason)
        self.text = text


@dataclass
class ActionContext:
    room: RoomInfo
    thread_id: str | None
    sender_name: str
    upload: Callable[[bytes, str, str], Awaitable[None]]
    approved: bool = False


@dataclass
class ActionResult:
    ok: bool
    summary: str = ""
    reason: str = ""  # when not ok
    text: str | None = None  # full receipt override
    silent: bool = False  # nothing to post (e.g. the screenshot caption is the receipt)
    detail: str = ""  # tail lines, posted in a fenced block
    warn: bool = False  # ⚠️ instead of ✅ (e.g. script exit != 0)


@dataclass
class BootResult:
    parts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        s = ", ".join(self.parts)
        for n in self.notes:
            s += f" · ⚠ {n}"
        return s


@dataclass
class Runtime:
    """Live facts about the agent that `status` reports."""

    frozen: bool = False
    queue_len: Callable[[], int] = lambda: 0
    role_held: Callable[[], bool] = lambda: False


class RoleOps:
    """Role operations implemented by the DeskAgent (RS-12 adds the lease renewal)."""

    async def assume_hands(self, room: RoomInfo) -> tuple[bool, str | None]:  # pragma: no cover
        return True, None

    async def release_hands(self) -> bool:  # pragma: no cover
        return True


from roomservice.desk.pageshot import capture_page  # noqa: E402  (RS-10: Playwright page shot)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "screen"


def _last_line(res: RunResult) -> str:
    text = (res.stderr_tail or res.stdout_tail).strip()
    return text.splitlines()[-1] if text else f"exit {res.code}"


class DeskActions:
    def __init__(
        self,
        cfg: DeskConfig,
        settings: Settings,
        adapter: OSAdapter,
        speech: Any,
        state: StateManager,
        roles: RoleOps | None = None,
        bus: Any = default_bus,
        runtime: Runtime | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        probe: Callable[[str], Awaitable[bool]] | None = None,
        webhook: Callable[[str], Awaitable[bool]] | None = None,
    ) -> None:
        self.cfg = cfg
        self.settings = settings
        self.adapter = adapter
        self.speech = speech
        self.state = state
        self.roles = roles or RoleOps()
        self.bus = bus
        self.runtime = runtime or Runtime()
        self.clock = clock
        self._sleep = sleep
        self._probe = probe or self._http_probe
        self._webhook = webhook or self._http_webhook
        self.page_shot: Callable[[str], Awaitable[bytes | None]] = capture_page
        self.started = clock()
        self.last_ignite: float | None = None
        self.last_project: str | None = None
        self.opened: dict[str, list[str]] = {"apps": [], "urls": [], "terminals": []}
        self.booted_opened: dict[str, dict[str, list[str]]] = {}
        self.dynamic: dict[str, discover.Detected] = {}  # RS-07: projects found on disk
        self.shell = ShellRunner()  # RS-07: approved `exec` only
        self.bg_procs: list[Any] = []  # RS-07: dev servers started by the desk

    # -- helpers ------------------------------------------------------------------------

    @property
    def dry(self) -> bool:
        return self.adapter.name == "dry"

    def speak(self, text: str) -> None:
        self.bus.publish(SpeakEvent(text=text))
        self.speech.say(text)

    def _known(self, name: str | None) -> Project | None:
        if not name:
            return None
        if name in self.cfg.projects:
            return self.cfg.projects[name]
        if name in self.dynamic:
            return self.dynamic[name].project
        a = self.state.active
        if a and a.project == name and a.path and Path(a.path).is_dir():  # after a restart
            self.dynamic[name] = discover.detect(name, Path(a.path))
            return self.dynamic[name].project
        return None

    def current_project(self) -> tuple[str, Project] | None:
        a = self.state.active
        for name in (a.project if a else None, self.last_project):
            if name and (p := self._known(name)) is not None:
                return name, p
        return None

    def _find(self, name: str) -> tuple[str, Project, discover.Detected | None]:
        """desk.yaml first, else a directory under the projects root(s) (RS-07)."""
        if name in self.cfg.projects:
            return name, self.cfg.projects[name], None
        r = discover.resolve_project(name)
        if isinstance(r, discover.Ambiguous):
            raise Reply("which one?", r.text)
        if isinstance(r, discover.NotFound):
            raise Reply(f"no project called {name}", r.text)
        self.dynamic[r.name] = r.detected
        return r.name, r.project, r.detected

    def app_target(self, key: str) -> str:
        t = self.cfg.apps[key]
        sysname = self.adapter.name
        if sysname == "dry":
            import platform

            sysname = {"Darwin": "macos", "Windows": "windows"}.get(platform.system(), "linux")
        return {"macos": t.mac, "windows": t.win}.get(sysname, t.linux)

    def _record(self, kind: str, value: str, project: str | None = None) -> None:
        if value not in self.opened[kind]:
            self.opened[kind].append(value)
        self.state.record_opened(kind, value)
        if project:
            bucket = self.booted_opened.setdefault(
                project, {"apps": [], "urls": [], "terminals": []}
            )
            if value not in bucket[kind]:
                bucket[kind].append(value)

    def _forget_opened(self) -> None:
        self.opened = {"apps": [], "urls": [], "terminals": []}
        self.booted_opened.clear()
        self.state.forget_booted()

    async def _http_probe(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                r = await c.get(url)
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    async def _http_webhook(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(url)
            return r.status_code < 400
        except httpx.HTTPError as e:
            log.warning("lights webhook failed: %s", type(e).__name__)
            return False

    # -- preflight (validation + approval need) -----------------------------------------

    def preflight(self, cmd: Command) -> tuple[str | None, str | None]:
        """Raises Refuse for invalid commands. Returns (approval_text, project) — approval_text
        is None when no approval is needed."""
        v, a = cmd.verb, cmd.args
        proj = self.current_project()
        pname = proj[0] if proj else None
        if v == "commit":
            if not " ".join(a).strip():
                raise Refuse('usage: commit "<message>"')
            self._need_project()
            return receipts.fmt_cmd("commit", [" ".join(a)]), pname
        if v == "push":
            if a:
                raise Refuse("push takes no arguments (never forced)")
            self._need_project()
            return "push", pname
        if v == "close":
            if len(a) != 1:
                raise Refuse("usage: close <app-key|all>")
            if a[0] == "all":
                return "close all", pname
            self._app(a[0])
        if v == "exec":  # RS-07: always approval-gated
            return receipts.fmt_cmd("exec", [self._exec_text(a)]), pname or "~"
        if v == "run":
            if len(a) != 1:
                raise Refuse("usage: run <script-key>")
            chk, script = allowlist.check_script(a[0], self.cfg)
            if not chk.ok or script is None:
                raise Refuse(chk.reason)
            if script.confirm:
                return receipts.fmt_cmd("run", [a[0]]), pname
        return None, pname

    def _need_project(self) -> tuple[str, Project]:
        proj = self.current_project()
        if proj is None:
            raise Refuse("no active project (start a task or boot one first)")
        return proj

    def _app(self, key: str) -> str:
        chk = allowlist.check_app(key, self.cfg)
        if not chk.ok:
            raise Refuse(chk.reason)
        return key

    # -- dispatch -----------------------------------------------------------------------

    async def execute(self, cmd: Command, ctx: ActionContext) -> ActionResult:
        if hasattr(self.adapter, "verb"):
            self.adapter.verb = cmd.verb
        handler = getattr(self, f"_v_{cmd.verb}", None)
        if handler is None:
            return ActionResult(False, reason=f"verb '{cmd.verb}' is not handled here")
        try:
            return await handler(cmd.args, ctx)
        except Refuse as e:
            return ActionResult(False, reason=str(e), text=getattr(e, "text", None))
        except Exception as e:  # one line, no stack trace in chat
            log.exception("action %s failed", cmd.verb)
            return ActionResult(False, reason=f"failed: {type(e).__name__}: {e}"[:200])

    # -- boot / resume ------------------------------------------------------------------

    async def lights(self, on: bool, project: str = "") -> str:
        """Webhook if configured, else a HUD flash (on only). Returns the mode used."""
        url = self.settings.lights_on_url if on else self.settings.lights_off_url
        if url:
            if self.dry:
                log.info("dry-run lights webhook %s", "on" if on else "off")
            else:
                await self._webhook(url)
            return "webhook"
        if on:
            self.bus.publish(IgnitionEvent(project=project or "lights", lights="flash"))
        else:
            self.bus.publish(SystemEvent(level="info", text="lights off (no webhook set)"))
        return "flash"

    def ignited_recently(self) -> bool:
        return self.last_ignite is not None and self.clock() - self.last_ignite < IGNITE_WINDOW_S

    async def boot(self, name: str) -> BootResult:
        if name in self.cfg.projects:
            return await self._boot_project(name, self.cfg.projects[name])
        if name in self.cfg.profiles:
            return await self._boot_profile(name)
        found, p, det = self._find(name)  # RS-07: any folder under the projects root
        return await self._boot_project(found, p, det)

    async def _open_editor(self, path: Path, res: BootResult, project: str) -> None:
        try:
            await self.adapter.open_in_editor(path)
            res.parts.append("editor")
            self._record("apps", "editor", project)
        except Exception as e:
            log.warning("code CLI failed (%s); falling back to apps.editor", e)
            if "editor" in self.cfg.apps:
                try:
                    await self.adapter.open_app(self.app_target("editor"))
                    res.parts.append("editor")
                    self._record("apps", "editor", project)
                    return
                except Exception as e2:
                    res.notes.append(f"editor failed ({e2})"[:80])
            else:
                res.notes.append("editor failed")

    async def _open_url_entry(self, entry: str, res: BootResult, project: str) -> int:
        chk = allowlist.resolve_project_url(entry, self.cfg)
        if not chk.ok:
            res.notes.append(f"url skipped: {entry}")
            return 0
        try:
            await self.adapter.open_url(chk.value)
        except Exception as e:
            res.notes.append(f"url failed: {chk.value} ({e})"[:80])
            return 0
        res.urls.append(chk.value)
        self._record("urls", chk.value, project)
        return 1

    async def _focus_step(self, res: BootResult) -> None:
        if await self.adapter.focus(True):
            res.parts.append("focus")
        else:
            res.notes.append("focus unsupported")

    async def _music_step(self, music: str, res: BootResult, project: str) -> None:
        try:
            if music.startswith("spotify:"):
                await self.adapter.open_url(music)
            else:
                await self.adapter.open_app(self.app_target("music"))
            res.parts.append("music")
            self._record("apps", "music", project)
        except Exception as e:
            res.notes.append(f"music failed ({e})"[:80])

    async def _boot_project(
        self, name: str, p: Project, det: discover.Detected | None = None
    ) -> BootResult:
        if not self.dry and not p.path.exists():
            raise Refuse(f"project path missing: {p.path}")
        res = BootResult()
        if p.lights and not self.ignited_recently():
            await self.lights(True, name)
        opened_xcode = det is not None and det.xcode is not None
        if opened_xcode:
            opened_xcode = await self._open_xcode(det, res, name)  # type: ignore[arg-type]
        if not opened_xcode and (p.open_editor or det is not None):
            await self._open_editor(p.path, res, name)
        fallback_ports = False
        if det is not None and det.dev_argv and not self.dry:
            url = await self._start_dev(det, res)
            if url:
                p = p.model_copy(update={"terminals": [], "urls": [url], "screenshot_url": url})
                self.dynamic[name] = replace(det, project=p, install_argv=None)
            else:
                fallback_ports = True
        n_term = 0
        for t in p.terminals:
            try:
                await self.adapter.open_terminal(p.path, t.cmd, t.name)
                n_term += 1
                self._record("terminals", t.name, name)
            except Exception as e:
                res.notes.append(f"terminal {t.name} failed ({e})"[:80])
        if n_term:
            res.parts.append(_plural(n_term, "terminal"))
        if fallback_ports and det is not None and (url := await self._probe_common_ports()):
            p = p.model_copy(update={"urls": [url], "screenshot_url": url})
            self.dynamic[name] = replace(det, project=p, install_argv=None)
        if p.wait_for and not self.dry and not await self._wait_for(p.wait_for):
            res.notes.append(f"{p.wait_for} not up after {WAIT_FOR_TIMEOUT_S}s")
        tabs = 0
        for entry in p.urls:
            tabs += await self._open_url_entry(entry, res, name)
        if tabs:
            res.parts.append(_plural(tabs, "tab"))
        if p.focus:
            await self._focus_step(res)
        if p.music:
            await self._music_step(p.music, res, name)
        self.state.mark_booted(name)
        self.last_project = name
        return res

    async def _open_xcode(self, det: discover.Detected, res: BootResult, project: str) -> bool:
        """Open the .xcworkspace/.xcodeproj with `open` (macOS) instead of the editor."""
        assert det.xcode is not None
        try:
            if self.adapter.name == "macos":
                r = await self.adapter.run(["open", str(det.xcode)], det.path, 30)
                if r.code != 0:
                    raise RuntimeError(_last_line(r))
            elif self.dry:
                await self.adapter.open_app("Xcode")
            else:
                res.notes.append("xcode needs macOS")
                return False
        except Exception as e:
            res.notes.append(f"xcode failed ({e})"[:80])
            return False
        res.parts.append("xcode")
        self._record("apps", "xcode", project)
        return True

    async def _start_dev(self, det: discover.Detected, res: BootResult) -> str | None:
        """Install deps if missing, run the dev command in the background, capture its URL."""
        if det.install_argv:
            r = await self.adapter.run(det.install_argv, det.path, 600)
            if r.code != 0:
                res.notes.append(f"{' '.join(det.install_argv)} failed: {_last_line(r)}"[:80])
                return None
            res.parts.append("deps")
        assert det.dev_argv
        url, proc = await discover.launch_dev_server(det.dev_argv, det.path)
        if url and proc:
            self.bg_procs.append(proc)
            res.parts.append("dev server")
            self._record("terminals", "dev", det.name)
            log.info("dev server for %s at %s", det.name, url)
        else:
            res.notes.append("no dev url in 45s, opened a terminal")
        return url

    async def _probe_common_ports(self) -> str | None:
        deadline = self.clock() + WAIT_FOR_TIMEOUT_S
        while True:
            for port in discover.COMMON_PORTS:
                if await self._probe(f"http://localhost:{port}"):
                    return f"http://localhost:{port}"
            if self.clock() >= deadline:
                return None
            await self._sleep(1.0)

    async def _boot_profile(self, name: str) -> BootResult:
        prof = self.cfg.profiles[name]
        res = BootResult()
        if prof.lights and not self.ignited_recently():
            await self.lights(True, name)
        n_apps = 0
        for key in prof.apps:
            if key not in self.cfg.apps:
                res.notes.append(f"app {key} not configured")
                continue
            try:
                await self.adapter.open_app(self.app_target(key))
                n_apps += 1
                self._record("apps", key, name)
            except Exception as e:
                res.notes.append(f"app {key} failed ({e})"[:80])
        if n_apps:
            res.parts.append(_plural(n_apps, "app"))
        tabs = 0
        for entry in prof.urls:
            tabs += await self._open_url_entry(entry, res, name)
        if tabs:
            res.parts.append(_plural(tabs, "tab"))
        if prof.focus:
            await self._focus_step(res)
        if prof.music:
            await self._music_step(prof.music, res, name)
        self.state.mark_booted(name)
        return res

    async def _wait_for(self, url: str) -> bool:
        deadline = self.clock() + WAIT_FOR_TIMEOUT_S
        while True:
            if await self._probe(url):
                return True
            if self.clock() >= deadline:
                return False
            await self._sleep(1.0)

    async def _v_boot(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1:
            raise Refuse("usage: boot <project>")
        res = await self.boot(a[0])
        return ActionResult(True, res.summary or "nothing to open")

    async def _v_resume(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1:
            raise Refuse("usage: resume <project>")
        name = self._find(a[0])[0]
        saved = self.state.latest_state(name)
        if self.state.is_booted(name):
            res = BootResult(parts=["already booted"], urls=list(
                self.booted_opened.get(name, {}).get("urls", [])))  # fmt: skip
        else:
            res = await self.boot(name)
        if saved:
            extra = [
                u for u in self.state.resume_extra_urls(saved, res.urls) if allowlist.url_allowed(u)
            ]
            opened = 0
            for u in extra:
                try:
                    await self.adapter.open_url(u)
                    self._record("urls", u, name)
                    opened += 1
                except Exception as e:
                    res.notes.append(f"url failed: {u} ({e})"[:80])
            if opened:
                res.parts.append(f"+{_plural(opened, 'tab')}")
        head = ((saved or {}).get("git") or {}).get("head")
        text = receipts.resume(name, res.summary, head=head, no_state=saved is None)
        return ActionResult(True, text=text)

    # -- mission / wrap -----------------------------------------------------------------

    async def _v_mission(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 2:
            raise Refuse("usage: task <name> <project|none>")
        slug, project = a[0], a[1]
        if not SLUG_RE.match(slug):
            raise Refuse("invalid task name")
        if project.lower() == "none":
            project = ""
        else:
            project = self._find(project)[0]
        ok, holder = await self.roles.assume_hands(ctx.room)
        if not ok:
            who = holder or "someone else"
            return ActionResult(False, reason=f"the computer is busy with {who}",
                                text=receipts.refused_held(who))  # fmt: skip
        p = self._known(project) if project else None
        auto = self.state.start_mission(
            slug, project or None, p.path if p else None, p.screenshot_url if p else None
        )
        if project:
            self.last_project = project
        if project and self.state.is_booted(project):
            for kind, vals in self.booted_opened.get(project, {}).items():
                for v in vals:
                    self.state.record_opened(kind, v)
            parts = None
        elif project:
            parts = (await self.boot(project)).summary
        else:
            parts = ""
        self.speak(f"Task {slug.replace('-', ' ')}. On it.")
        self.bus.publish(MissionEvent(slug=slug, started_at=now_ms()))
        extra = f" · auto-wrapped {auto['slug']}" if auto else ""
        if parts is None:
            return ActionResult(True, text=receipts.mission_already_booted(slug) + extra)
        summary = (parts + " · " if parts else "") + "computer assumed" + extra
        return ActionResult(True, summary=summary)

    async def _v_wrap(self, a: list[str], ctx: ActionContext) -> ActionResult:
        try:
            state = self.state.wrap()
        except NoActiveMission:
            raise Refuse("no active task") from None
        self._forget_opened()
        text = receipts.wrap(state["slug"], state["mission_minutes"], state)
        return ActionResult(True, text=text)

    # -- simple verbs -------------------------------------------------------------------

    async def _v_open(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1:
            raise Refuse("usage: open <app-key>")
        key = self._app(a[0])
        await self.adapter.open_app(self.app_target(key))
        self._record("apps", key)
        return ActionResult(True, self.app_target(key))

    async def _v_url(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1:
            raise Refuse("usage: url <alias|url>")
        chk = allowlist.check_url(a[0], self.cfg)
        if not chk.ok:
            raise Refuse(chk.reason)
        await self.adapter.open_url(chk.value)
        self._record("urls", chk.value)
        return ActionResult(True, chk.value)

    async def _v_run(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1:
            raise Refuse("usage: run <script-key>")
        chk, script = allowlist.check_script(a[0], self.cfg)
        if not chk.ok or script is None:
            raise Refuse(chk.reason)
        if script.cwd == "project":
            cwd = self._need_project()[1].path
        else:
            cwd = Path.home()
        res = await self.adapter.run(list(script.cmd), cwd, script.timeout_s)
        tail = "\n".join(x for x in (res.stdout_tail, res.stderr_tail) if x)
        return ActionResult(True, summary=f"exit {res.code}", detail=tail, warn=res.code != 0)

    # -- RS-07: free-form exec (approval-gated) and project listing ----------------------

    @staticmethod
    def _exec_text(args: list[str]) -> str:
        text = " ".join(args).strip()
        if not text:
            raise Refuse('usage: exec "<command>"')
        if len(text) > EXEC_MAX_CHARS:
            raise Refuse(f"command longer than {EXEC_MAX_CHARS} chars")
        if any(c in text for c in "\n\r\0"):
            raise Refuse("one line only")
        return text

    def exec_cwd(self) -> Path:
        a = self.state.active
        if a and a.project and a.path and Path(a.path).is_dir():
            return Path(a.path)
        return discover.first_root() or Path.home()

    def kill_exec(self) -> bool:
        return self.shell.kill()

    async def _v_exec(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if not ctx.approved:
            raise Refuse("exec needs approval")
        text = self._exec_text(a)
        cwd = self.exec_cwd()
        if self.dry:
            res = await self.adapter.run(["bash", "-lc", text], cwd, EXEC_TIMEOUT_S)
        else:
            res = await self.shell.run(text, cwd, EXEC_TIMEOUT_S)
        out = "\n".join(x for x in (res.stdout_tail, res.stderr_tail) if x)
        out = "\n".join(out.splitlines()[-15:])
        return ActionResult(True, summary=f"exit {res.code}", detail=out, warn=res.code != 0)

    async def _v_projects(self, a: list[str], ctx: ActionContext) -> ActionResult:
        return ActionResult(True, summary=discover.projects_text(self.cfg))

    async def _v_focus(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1 or a[0].lower() not in ("on", "off"):
            raise Refuse("usage: focus on|off")
        on = a[0].lower() == "on"
        if not await self.adapter.focus(on):
            raise Refuse("focus unsupported on this machine")
        return ActionResult(True, "focus on" if on else "focus off")

    async def _v_say(self, a: list[str], ctx: ActionContext) -> ActionResult:
        text = " ".join(a).strip()
        if not text:
            raise Refuse('usage: say "<text>"')
        if len(text) > SAY_MAX:
            raise Refuse(f"text longer than {SAY_MAX} chars")
        self.speak(text)
        return ActionResult(True, "spoken")

    async def _v_close(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1:
            raise Refuse("usage: close <app-key|all>")
        if a[0] == "all":
            if not ctx.approved:
                raise Refuse("close all needs approval")
            keys = list(self.opened["apps"])
            for key in keys:
                try:
                    await self.adapter.quit_app(self.app_target(key))
                except Exception as e:
                    log.warning("quit %s failed: %s", key, e)
            self._forget_opened()
            return ActionResult(True, f"closed {_plural(len(keys), 'app')}")
        key = self._app(a[0])
        await self.adapter.quit_app(self.app_target(key))
        if key in self.opened["apps"]:
            self.opened["apps"].remove(key)
        return ActionResult(True, f"closed {self.app_target(key)}")

    async def _git(self, argv: list[str], cwd: Path) -> RunResult:
        return await self.adapter.run(argv, cwd, GIT_TIMEOUT_S)

    async def _v_commit(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if not ctx.approved:
            raise Refuse("commit needs approval")
        msg = " ".join(a).strip()
        if not msg:
            raise Refuse('usage: commit "<message>"')
        cwd = self._need_project()[1].path
        res = await self._git(["git", "add", "-A"], cwd)
        if res.code != 0:
            raise Refuse(f"git add failed: {_last_line(res)}")
        res = await self._git(["git", "commit", "-m", msg], cwd)
        if res.code != 0:
            raise Refuse(f"git commit failed: {_last_line(res)}")
        first = (res.stdout_tail.splitlines() or ["committed"])[0]
        return ActionResult(True, first)

    async def _v_push(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if not ctx.approved:
            raise Refuse("push needs approval")
        if a:
            raise Refuse("push takes no arguments (never forced)")
        cwd = self._need_project()[1].path
        res = await self._git(["git", "push"], cwd)
        if res.code != 0:
            raise Refuse(f"git push failed: {_last_line(res)}")
        return ActionResult(True, "pushed")

    async def _v_lights(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if len(a) != 1 or a[0].lower() not in ("on", "off"):
            raise Refuse("usage: lights on|off")
        on = a[0].lower() == "on"
        proj = self.current_project()
        mode = await self.lights(on, proj[0] if proj else "")
        return ActionResult(True, f"lights {'on' if on else 'off'} ({mode})")

    async def _v_release(self, a: list[str], ctx: ActionContext) -> ActionResult:
        if not await self.roles.release_hands():
            raise Refuse("the computer is not on the job here")
        return ActionResult(True, "computer released")

    async def _v_help(self, a: list[str], ctx: ActionContext) -> ActionResult:
        return ActionResult(True, text=HELP_TEXT)

    async def _v_status(self, a: list[str], ctx: ActionContext) -> ActionResult:
        m = self.state.active
        proj = self.current_project()
        up_min = int((self.clock() - self.started) / 60)
        bits = [
            f"task {m.slug}" if m else "no task",
            f"project {proj[0]} ({proj[1].path})" if proj else "no project",
        ]
        if proj and proj[1].screenshot_url:
            bits.append(f"dev {proj[1].screenshot_url}")
        bits += [
            "apps: " + (", ".join(self.opened["apps"]) or "none"),
            f"up {up_min}m",
            f"queue {self.runtime.queue_len()}",
            f"paused {'yes' if self.runtime.frozen else 'no'}",
            f"computer on the job: {'yes' if self.runtime.role_held() else 'no'}",
        ]
        return ActionResult(True, summary=" · ".join(bits))

    # -- screenshots --------------------------------------------------------------------

    async def _v_shot(self, a: list[str], ctx: ActionContext) -> ActionResult:
        kind = a[0].lower() if a else None
        if kind not in (None, "screen", "page") or len(a) > 1:
            raise Refuse("usage: shot [screen|page]")
        proj = self.current_project()
        url = proj[1].screenshot_url if proj else None
        if kind is None:
            kind = "page" if url else "screen"
        png: bytes | None = None
        fallback = False
        if kind == "page":
            if url:
                try:
                    png = await self.page_shot(url)
                except Exception as e:
                    log.warning("page screenshot failed: %s", e)
            fallback = png is None
        if png is None:
            png = await self.adapter.screenshot_screen()
        as_page = kind == "page" and not fallback
        label = proj[0] if as_page and proj else "screen"
        now = datetime.now(receipts.IST)
        caption = receipts.screenshot_caption(label, url if as_page else None, now)
        if fallback:
            caption += " (screen fallback)"
        filename = f"shot-{_slug(label)}-{now:%H%M%S}.png"
        (store.shots_dir() / filename).write_bytes(png)
        self.bus.publish(ScreenshotEvent(url=f"/shots/{filename}", caption=caption))
        await ctx.upload(png, filename, caption)
        return ActionResult(True, "uploaded", silent=True)
