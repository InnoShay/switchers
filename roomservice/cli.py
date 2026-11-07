"""typer CLI (SPEC §11.9). Commands are added by their tickets (RS-03, RS-07, ...)."""

import typer

app = typer.Typer(
    name="roomservice",
    help="RoomService: give your room a body with Switch.",
    no_args_is_help=True,
    add_completion=False,
)
