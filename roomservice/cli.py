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
