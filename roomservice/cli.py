"""typer CLI (SPEC §11.9). Commands are added by their tickets (RS-03, RS-07, ...)."""

import asyncio

import typer
from rich.console import Console

from roomservice import store
from roomservice.contracts.config import load_settings
from roomservice.contracts.switch import OpError
from roomservice.switch.http import SwitchHTTPClient

app = typer.Typer(
    name="roomservice",
    help="RoomService: give your room a body with Switch.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()

# -- register (RS-03, SPEC §11.3) -----------------------------------------------------------

_DESK_DESC = (
    "RoomService desk agent. Acts on this computer through an allowlist. "
    "Speaks the hands grammar only."
)
# name -> (display_name, connector_type, description)
REGISTRABLE: dict[str, tuple[str, str, str]] = {
    "desk-laptop": ("Hands · laptop", "roomservice-desk", _DESK_DESC),
    "desk-backup": ("Hands · backup", "roomservice-desk", _DESK_DESC),
    "life": (
        "Life",
        "roomservice-life",
        "Calendar and email through n8n. Creates events and drafts; never sends email.",
    ),
}
DEFAULT_REGISTER = ["desk-laptop", "life"]


async def _register_all(names: list[str], overwrite: bool) -> list[str]:
    """Register `names`; returns the names that now have credentials stored."""
    settings = load_settings()
    if settings.switch_registration_key is None:
        console.print("[red]SWITCH_REGISTRATION_KEY is not set in .env[/red] (Gateway → API Keys)")
        raise typer.Exit(1)
    url = str(settings.switch_url).rstrip("/")
    reg = SwitchHTTPClient(
        url, registration_key=settings.switch_registration_key.get_secret_value()
    )
    done: list[str] = []
    try:
        for name in names:
            display, connector, desc = REGISTRABLE[name]
            try:
                agent_id, key = await reg.register(name, display, desc, connector, overwrite)
            except OpError as e:
                if e.status == 409:
                    have = store.load_agent_creds(url, name) is not None
                    console.print(
                        f"[yellow]{name}: already registered"
                        f"{' (local key kept)' if have else ' but no local key'}; "
                        "re-run with --overwrite to rotate the key.[/yellow]"
                    )
                    if have:
                        done.append(name)
                    continue
                console.print(f"[red]{name}: {e}[/red]")
                continue
            store.save_agent_creds(url, name, agent_id, key)
            agent_http = SwitchHTTPClient(url, agent_id=agent_id, api_key=key)
            try:
                await agent_http.op(
                    "update_agent_detail",
                    {"agent_id": agent_id, "addressing": "owner_and_owner_agents"},
                )
            except OpError as e:
                console.print(f"[yellow]{name}: could not set addressing ({e})[/yellow]")
            finally:
                await agent_http.aclose()
            console.print(f"[green]registered[/green] {name} (id {agent_id}; key saved, not shown)")
            done.append(name)
    finally:
        await reg.aclose()
    return done


@app.command()
def register(
    agent: str = typer.Option(
        "all", "--agent", help="desk-laptop | life | desk-backup | all (= desk-laptop + life)"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Rotate the key if it exists"),
) -> None:
    """Register runtime agents with Switch and store their keys in ~/.roomservice/agents.json."""
    if agent == "all":
        names = list(DEFAULT_REGISTER)
    elif agent in REGISTRABLE:
        names = [agent]
    else:
        console.print(
            f"[red]unknown agent '{agent}'; use desk-laptop, life, desk-backup, all[/red]"
        )
        raise typer.Exit(2)
    try:
        done = asyncio.run(_register_all(names, overwrite))
    except OpError as e:
        console.print(f"[red]Switch refused: {e}[/red] Check SWITCH_REGISTRATION_KEY.")
        raise typer.Exit(1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]{type(e).__name__}: {e}[/red] Is SWITCH_URL reachable?")
        raise typer.Exit(1) from e
    if done:
        console.print(
            "\nIn Mattermost roomservice-hq (and the Telegram group) send, one per message:"
        )
        for name in done:
            console.print(f"  !invite-agent @{name}")
    if len(done) != len(names):
        raise typer.Exit(1)


# -- spike (RS-03, SPEC §20.1) ---------------------------------------------------------------


@app.command()
def spike(which: str = typer.Argument(..., help="s0 .. s8")) -> None:
    """Run one Switch spike (SPEC §20.1). Record the result in DECISIONS.md."""
    from roomservice.spikes import run_spike

    if not run_spike(which):
        raise typer.Exit(1)


# -- pair / up / say / doctor (RS-07, SPEC §9.5, §11.9, §19, §20.7) --------------------------


def _load_cfg(settings):
    from roomservice.contracts.config import ConfigError, load_desk_config

    try:
        return load_desk_config(settings.roomservice_desk_config)
    except ConfigError as e:
        console.print(f"[red]desk.yaml: {e}[/red]")
        console.print("Fix: cp config/desk.example.yaml config/desk.yaml and edit the paths.")
        raise typer.Exit(1) from e


@app.command()
def pair() -> None:
    """Print a 6-digit pairing code (10 min) and wait for owners to pair from chat."""
    import time

    from roomservice.agents.desk import PAIR_TTL_S, load_owners, new_pairing_code

    code = new_pairing_code()
    console.print(f"Pairing code: [bold]{code}[/bold]  (valid {PAIR_TTL_S // 60} min)")
    console.print(
        "From each surface (Mattermost and Telegram) post in an HQ room: "
        f"[bold]@hands pair {code}[/bold]"
    )
    console.print("Waiting... Ctrl-C when done.")
    seen = {(o["sender"], o.get("room_name")) for o in load_owners()}
    end = time.time() + PAIR_TTL_S
    try:
        while time.time() < end:
            for o in load_owners():
                key = (o["sender"], o.get("room_name"))
                if key not in seen:
                    seen.add(key)
                    console.print(
                        f"[green]paired[/green] {o.get('sender_name')} on {o.get('room_name')}"
                    )
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    console.print("Done.")


def _optional(module: str, attr: str):
    """Import `module.attr`; None (and a log line) if it is not built yet."""
    import importlib

    try:
        return getattr(importlib.import_module(module), attr)
    except (ImportError, AttributeError):
        console.print(f"[yellow]skipped: {module}.{attr} not built yet[/yellow]")
        return None


def _call_flexible(fn, **candidates):
    """Call fn with only the keyword arguments its signature accepts."""
    import inspect

    params = inspect.signature(fn).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**candidates)
    return fn(**{k: v for k, v in candidates.items() if k in params})


def _open_hud(port: int) -> None:
    """SPEC §16.1 auto-open: Chrome app window on macOS if installed, else the default browser."""
    import platform
    import subprocess
    import webbrowser
    from pathlib import Path

    url = f"http://127.0.0.1:{port}"
    if platform.system() == "Darwin" and Path("/Applications/Google Chrome.app").exists():
        subprocess.Popen(
            ["open", "-na", "Google Chrome", "--args", f"--app={url}", "--start-fullscreen"]
        )
    else:
        webbrowser.open(url)


def _status_table(agent) -> None:
    from rich.table import Table

    s = agent.status_snapshot()
    t = Table(title="roomservice", show_header=False)
    t.add_row(
        "rooms", f"{s['rooms']} (HQ: {', '.join(s['hq']) or '-'}; missions: {len(s['missions'])})"
    )
    t.add_row("role", s["role"])
    t.add_row("queue", str(s["queue"]) + (" · FROZEN" if s["frozen"] else ""))
    t.add_row("last error", s["last_error"] or "-")
    console.print(t)


async def _up(dry_run: bool, no_hud: bool, no_life: bool) -> None:
    import contextlib

    from roomservice.agents.desk import DeskAgent
    from roomservice.log import setup_logging

    setup_logging()
    settings = load_settings()
    dry = dry_run or settings.roomservice_dry_run
    cfg = _load_cfg(settings)
    agent = DeskAgent(cfg=cfg, settings=settings, dry_run=dry)
    stoppables: list = []
    bg: list[asyncio.Task] = []
    scheduler = None
    await agent.start()
    stoppables.append(agent)
    console.print(f"[green]desk up[/green] as {agent.name}{' (dry run)' if dry else ''}")

    hud_started = False
    if not no_hud:
        run_hud = _optional("roomservice.hud.server", "run_hud")
        if run_hud is not None:
            try:
                res = _call_flexible(run_hud, port=settings.hud_port, settings=settings)
                if asyncio.iscoroutine(res):
                    bg.append(asyncio.create_task(res))
                hud_started = True
            except Exception as e:
                console.print(f"[yellow]HUD failed to start: {e}[/yellow]")
    if hud_started:
        _open_hud(settings.hud_port)

    if not no_life:
        life_cls = _optional("roomservice.agents.life", "LifeAgent")
        if life_cls is not None:
            try:
                life = _call_flexible(life_cls, settings=settings)
                await life.start()
                stoppables.append(life)
            except (Exception, SystemExit) as e:
                console.print(f"[yellow]life skipped: {e}[/yellow]")
        start_sched = _optional("roomservice.scheduler", "start_scheduler")
        if start_sched is not None:
            try:
                scheduler = _call_flexible(
                    start_sched, settings=settings, cfg=cfg, desk=agent, agent=agent
                )
                if asyncio.iscoroutine(scheduler):
                    scheduler = await scheduler
            except Exception as e:
                console.print(f"[yellow]scheduler skipped: {e}[/yellow]")

    try:
        while True:
            await asyncio.sleep(60)
            _status_table(agent)
    finally:
        for t in bg:
            t.cancel()
        if scheduler is not None and hasattr(scheduler, "shutdown"):
            with contextlib.suppress(Exception):
                scheduler.shutdown(wait=False)
        for s in reversed(stoppables):
            with contextlib.suppress(Exception):
                await s.stop()


@app.command()
def up(
    dry_run: bool = typer.Option(False, "--dry-run", help="Fake OS actions (no real apps/speech)"),
    no_hud: bool = typer.Option(False, "--no-hud", help="Do not start the HUD"),
    no_life: bool = typer.Option(False, "--no-life", help="Do not start life/scheduler"),
) -> None:
    """Start the desk (hands), plus HUD/life/scheduler when they exist."""
    try:
        asyncio.run(_up(dry_run, no_hud, no_life))
    except KeyboardInterrupt:
        console.print("bye")
    except (SystemExit, typer.Exit):
        raise
    except Exception as e:
        console.print(f"[red]{type(e).__name__}: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def backup(dry_run: bool = typer.Option(False, "--dry-run", help="Fake OS actions")) -> None:
    """Run the backup desk (desk-backup, no life/scheduler); takes `hands` on handoff (SPEC §15)."""
    from roomservice.agents.backup import run_backup

    try:
        asyncio.run(run_backup(dry_run))
    except KeyboardInterrupt:
        console.print("bye")


@app.command()
def say(text: str = typer.Argument(..., help="Text to speak")) -> None:
    """Local TTS test with the configured voice."""
    from roomservice.contracts.config import Voice, load_desk_config
    from roomservice.desk.os import get_adapter

    voice = Voice()
    try:
        voice = load_desk_config(load_settings().roomservice_desk_config).voice
    except Exception:
        pass
    asyncio.run(get_adapter(False).speak(text, voice.voice_name, voice.rate))


@app.command()
def doctor() -> None:
    """Check the whole setup; every line is ✅ or ❌ with a fix."""
    from roomservice.doctor import format_result, run_doctor

    settings = load_settings()
    results = asyncio.run(run_doctor(settings))
    for r in results:
        console.print(format_result(r), markup=False, highlight=False)
    if not all(r.ok for r in results):
        raise typer.Exit(1)


@app.command("build-templates")
def build_templates() -> None:
    """Build switch/templates/dist/*.yaml from the templates and instruction files."""
    from roomservice.templates_build import run_build_templates

    run_build_templates()
