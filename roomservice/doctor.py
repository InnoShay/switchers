"""`roomservice doctor` (SPEC §20.7): ✅/❌ with a fix hint for each check.

Every check is isolated: an exception becomes a ❌ line, never a crash. Checks that depend on
something not built yet (HUD, n8n workflow, desk.yaml) degrade to a ❌ with the fix.
"""

from __future__ import annotations

import asyncio
import io
import platform
import shutil
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from roomservice import store
from roomservice.contracts.agent import RoomKind
from roomservice.contracts.config import ConfigError, DeskConfig, Settings, load_desk_config
from roomservice.switch.http import SwitchHTTPClient
from roomservice.switch.rooms import detect_kind, parse_rooms


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    hint: str = ""


Check = Callable[[], Awaitable[CheckResult]]


def _ok(name: str, detail: str = "") -> CheckResult:
    return CheckResult(name, True, detail)


def _bad(name: str, detail: str, hint: str) -> CheckResult:
    return CheckResult(name, False, detail, hint)


def non_dark_fraction(png: bytes, threshold: int = 40) -> float:
    """Share of pixels whose brightest channel exceeds `threshold` (downscaled)."""
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGB").resize((160, 100))
    px = list(img.getdata())
    return sum(1 for p in px if max(p) > threshold) / max(1, len(px))


def mac_app_installed(name: str) -> bool:
    return any(
        (Path(base) / f"{name}.app").exists()
        for base in ("/Applications", str(Path.home() / "Applications"))
    )


def playwright_chromium_installed() -> bool:
    import os

    roots: list[Path] = []
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        roots.append(Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]))
    home = Path.home()
    roots += [
        home / "Library/Caches/ms-playwright",
        home / ".cache/ms-playwright",
        home / "AppData/Local/ms-playwright",
    ]
    return any(r.is_dir() and any(r.glob("chromium*")) for r in roots)


class Doctor:
    def __init__(self, settings: Settings, desk_config_path: Path | None = None) -> None:
        self.s = settings
        self.url = str(settings.switch_url).rstrip("/")
        self.cfg_path = desk_config_path or settings.roomservice_desk_config
        self.cfg: DeskConfig | None = None
        self.cfg_error: str | None = None
        try:
            self.cfg = load_desk_config(self.cfg_path)
        except ConfigError as e:
            self.cfg_error = str(e)

    # -- switch -------------------------------------------------------------------------

    async def switch_health(self) -> CheckResult:
        c = SwitchHTTPClient(self.url)
        try:
            ok = await c.health()
        finally:
            await c.aclose()
        if ok:
            return _ok("Switch health", self.url)
        return _bad(
            "Switch health",
            f"{self.url}/health failed",
            "Start Switch Console; fix SWITCH_URL in .env",
        )

    async def registration_key(self) -> CheckResult:
        if self.s.switch_registration_key is None:
            return _bad(
                "Registration key", "SWITCH_REGISTRATION_KEY not set",
                "Gateway → API Keys → create a registration key; put it in .env",
            )  # fmt: skip
        return _ok("Registration key", "set (only `roomservice register` can prove it works)")

    async def agents_json(self) -> CheckResult:
        have = store.read_json(store.agents_path(), {}).get(self.url, {})
        want = self.s.roomservice_agent
        if want in have:
            return _ok("agents.json", f"{', '.join(sorted(have))} for {self.url}")
        return _bad(
            "agents.json", f"no '{want}' for {self.url}", "Run `uv run roomservice register`"
        )

    async def agent_keys(self) -> CheckResult:
        have = store.read_json(store.agents_path(), {}).get(self.url, {})
        if not have:
            return _bad("Agent keys", "no agents registered", "Run `uv run roomservice register`")
        bad: list[str] = []
        for name, cred in have.items():
            c = SwitchHTTPClient(self.url, agent_id=cred["id"], api_key=cred["api_key"])
            try:
                await c.list_ops()
            except Exception:
                bad.append(name)
            finally:
                await c.aclose()
        if bad:
            return _bad(
                "Agent keys",
                f"rejected: {', '.join(bad)}",
                "Run `uv run roomservice register --overwrite`",
            )
        return _ok("Agent keys", ", ".join(sorted(have)))

    async def rooms_visible(self) -> CheckResult:
        cred = store.load_agent_creds(self.url, self.s.roomservice_agent)
        if not cred:
            return _bad("Rooms visible", "no desk credentials", "Run `uv run roomservice register`")
        c = SwitchHTTPClient(self.url, agent_id=cred["id"], api_key=cred["api_key"])
        try:
            raw = parse_rooms(await c.op("list_rooms", {}))
        finally:
            await c.aclose()
        names = []
        hq = 0
        for r in raw:
            rid = str(r.get("id") or r.get("room_id"))
            name = str(r.get("name") or rid)
            is_hq = detect_kind(rid, name, self.s.roomservice_hq_rooms) == RoomKind.HQ
            hq += is_hq
            names.append(f"{name}{' [HQ]' if is_hq else ''}")
        if not hq:
            return _bad(
                "Rooms visible", f"{len(raw)} rooms, none is HQ",
                "Invite the agent: `!invite-agent @desk-laptop` in roomservice-hq",
            )  # fmt: skip
        return _ok("Rooms visible", ", ".join(names))

    async def owners_paired(self) -> CheckResult:
        from roomservice.agents.base import owner_ids

        n = len(owner_ids())
        if n:
            return _ok("Owners paired", f"{n} owner id(s)")
        return _bad(
            "Owners paired",
            "none",
            "Run `uv run roomservice pair`, then `@hands pair <code>` in HQ",
        )

    # -- config -------------------------------------------------------------------------

    async def desk_yaml(self) -> CheckResult:
        if self.cfg:
            return _ok("desk.yaml", str(self.cfg_path))
        return _bad(
            "desk.yaml", self.cfg_error or "unreadable",
            "cp config/desk.example.yaml config/desk.yaml and fix the path above",
        )  # fmt: skip

    async def project_paths(self) -> CheckResult:
        if not self.cfg:
            return _bad("Project paths", "desk.yaml not loaded", "Fix desk.yaml first")
        missing = [f"{n}: {p.path}" for n, p in self.cfg.projects.items() if not p.path.exists()]
        if missing:
            return _bad(
                "Project paths",
                "; ".join(missing),
                "Create the folder or fix `path:` (setup_mac.sh seeds demo/volt)",
            )
        return _ok("Project paths", f"{len(self.cfg.projects)} project(s)")

    # -- machine ------------------------------------------------------------------------

    async def code_on_path(self) -> CheckResult:
        if shutil.which("code") or shutil.which("code.cmd"):
            return _ok("`code` on PATH")
        return _bad(
            "`code` on PATH",
            "not found",
            "VS Code → Cmd+Shift+P → 'Shell Command: Install code in PATH'",
        )

    async def apps_installed(self) -> CheckResult:
        sysname = platform.system()
        if sysname == "Darwin":
            missing = [a for a in ("Google Chrome", "Spotify") if not mac_app_installed(a)]
        else:
            missing = [
                name
                for name, bins in (
                    ("Chrome", ("google-chrome", "chrome")),
                    ("Spotify", ("spotify",)),
                )
                if not any(shutil.which(x) for x in bins)
            ]
        if missing:
            return _bad(
                "Chrome / Spotify",
                f"missing: {', '.join(missing)}",
                "Install them (music step and HUD window need them)",
            )
        return _ok("Chrome / Spotify")

    async def screen_recording(self) -> CheckResult:
        from roomservice.desk.os import get_adapter

        png = await get_adapter(False).screenshot_screen()
        frac = non_dark_fraction(png)
        if frac > 0.02:
            return _ok("Screen Recording", f"{frac:.0%} non-dark pixels")
        return _bad(
            "Screen Recording", f"screenshot looks blank ({frac:.1%} non-dark)",
            "System Settings → Privacy → Screen Recording → enable your terminal",
        )  # fmt: skip

    async def shortcuts(self) -> CheckResult:
        if platform.system() != "Darwin":
            return _ok("Focus shortcuts", "n/a (macOS only)")
        try:
            proc = await asyncio.create_subprocess_exec(
                "shortcuts", "list",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            out, _ = await asyncio.wait_for(proc.communicate(), 20)
        except (OSError, TimeoutError):
            return _bad(
                "Focus shortcuts", "`shortcuts` failed", "Open the Shortcuts app once (macOS 12+)"
            )
        listing = out.decode("utf-8", "replace")
        missing = [n for n in ("RoomService Focus On", "RoomService Focus Off") if n not in listing]
        if missing:
            return _bad(
                "Focus shortcuts", f"missing: {', '.join(missing)}",
                "Shortcuts app → create 'RoomService Focus On/Off' (Set Focus action)",
            )  # fmt: skip
        return _ok("Focus shortcuts")

    async def n8n(self) -> CheckResult:
        url = str(self.s.n8n_life_url)
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    url,
                    headers={"X-RoomService-Token": self.s.n8n_life_token.get_secret_value()},
                    json={"mode": "ask", "text": "ping"},
                )
        except httpx.HTTPError:
            return _bad(
                "n8n", f"not reachable at {url}",
                "docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d",
            )  # fmt: skip
        if r.status_code == 200:
            return _ok("n8n", "reachable, token accepted")
        return _bad(
            "n8n", f"HTTP {r.status_code}", "Check N8N_LIFE_TOKEN and that the workflow is Active"
        )

    async def playwright(self) -> CheckResult:
        if playwright_chromium_installed():
            return _ok("Playwright chromium")
        return _bad(
            "Playwright chromium",
            "not installed",
            "uv run playwright install chromium (page screenshots; falls back to screen)",
        )

    async def tts(self) -> CheckResult:
        sysname = platform.system()
        tool = {"Darwin": "say", "Windows": "powershell"}.get(sysname, "espeak")
        if shutil.which(tool):
            return _ok("TTS", tool)
        return _bad(
            "TTS", f"`{tool}` not found", "Install espeak (Linux) or set voice.enabled: false"
        )

    async def hud_port(self) -> CheckResult:
        port = self.s.hud_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                return _bad(
                    "HUD port",
                    f"{port} in use",
                    "Stop the other process (is `roomservice up` running?) or set HUD_PORT",
                )
        return _ok("HUD port", f"{port} free")

    # -- run ----------------------------------------------------------------------------

    def checks(self) -> list[Check]:
        return [
            self.switch_health, self.registration_key, self.agents_json, self.agent_keys,
            self.rooms_visible, self.owners_paired, self.desk_yaml, self.project_paths,
            self.code_on_path, self.apps_installed, self.screen_recording, self.shortcuts,
            self.n8n, self.playwright, self.tts, self.hud_port,
        ]  # fmt: skip

    async def run(self) -> list[CheckResult]:
        out: list[CheckResult] = []
        for chk in self.checks():
            name = chk.__name__.replace("_", " ")
            try:
                out.append(await asyncio.wait_for(chk(), 30))
            except Exception as e:
                out.append(
                    _bad(
                        name, f"{type(e).__name__}: {e}"[:160], "See the log; fix and re-run doctor"
                    )
                )
        return out


async def run_doctor(settings: Settings, desk_config_path: Path | None = None) -> list[CheckResult]:
    return await Doctor(settings, desk_config_path).run()


def format_result(r: CheckResult) -> str:
    mark = "✅" if r.ok else "❌"
    tail = f" — {r.detail}" if r.detail else ""
    hint = f"\n     fix: {r.hint}" if (not r.ok and r.hint) else ""
    return f"{mark} {r.name}{tail}{hint}"


__all__: list[Any] = ["CheckResult", "Doctor", "run_doctor", "format_result"]
