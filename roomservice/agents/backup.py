"""BackupAgent (SPEC §15): the same DeskAgent on the second machine, polling for `hands`."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from roomservice.agents.desk import DeskAgent, hands_holder
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.events import SystemEvent, TransferEvent
from roomservice.contracts.switch import MessagePayload, OpError
from roomservice.desk import receipts
from roomservice.log import get_logger
from roomservice.switch.rooms import _activity, parse_rooms

log = get_logger("backup")

BACKUP_NAME = "desk-backup"
POLL_S = 5.0


def newest_mission(rooms: list[RoomInfo], raw_rooms: list[dict]) -> RoomInfo | None:
    """The newest `mission-*` / `task-*` room: by activity, then list position."""
    by_id = {r.id: r for r in rooms if r.kind == RoomKind.MISSION}
    best: tuple[float, int, RoomInfo] | None = None
    for i, raw in enumerate(raw_rooms):
        info = by_id.get(str(raw.get("id") or raw.get("room_id")))
        if info is None:
            continue
        key = (_activity(raw), i)
        if best is None or key > best[:2]:
            best = (key[0], key[1], info)
    return best[2] if best else None


class BackupAgent(DeskAgent):
    """desk-backup: no life, no scheduler, no ignition. Takes `hands` when the laptop lets go.

    Modes (ROOMSERVICE_HANDOFF_MODE): `lease` also tries to assume while hands is shown as held
    (it only succeeds once the laptop's lease lapsed); `explicit` waits until it is unheld,
    i.e. until the owner sends `@hands release` to the laptop.
    """

    def __init__(self, **kw: Any) -> None:
        kw.setdefault("name", BACKUP_NAME)
        super().__init__(**kw)
        self.poll_every_s = POLL_S
        # One ignition per wake phrase is the laptop's job.
        self.ignition.matches = lambda room, msg: False  # type: ignore[method-assign]

    def wants_unaddressed(self, room: RoomInfo, msg: MessagePayload) -> bool:
        # Approvals are resolved where the command ran; only act unaddressed while holding hands.
        return self.role_room is not None and super().wants_unaddressed(room, msg)

    async def start(self) -> None:
        await super().start()
        self._tasks.append(asyncio.create_task(self._handoff_loop(), name="backup-handoff"))

    async def _handoff_loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_every_s)
            try:
                await self.poll_handoff()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # the poll must survive anything
                self.last_error = f"handoff poll: {type(e).__name__}: {e}"[:200]
                log.warning("handoff poll failed: %s", e)

    async def poll_handoff(self) -> bool:
        """One 5-s tick. True when this call moved `hands` onto this machine."""
        if self.role_room is not None:
            return False
        raw_rooms = parse_rooms(await self.http.op("list_rooms", {}))
        room = newest_mission(self.rooms(), raw_rooms)
        if room is None or not room.conn_id:
            return False
        try:
            holder = hands_holder(await self.http.op("list_roles", {}, room.conn_id))
        except OpError as e:
            log.warning("list_roles failed: %s", e)
            return False
        if holder is not None and (holder == self.name or holder == self.self_id):
            self.role_room = room  # restarted while already holding it
            return False
        lease_mode = self.settings.roomservice_handoff_mode == "lease"
        if holder is not None and not lease_mode:
            return False
        try:
            await self.http.op("assume_role", {"role": "hands"}, room.conn_id)
        except OpError as e:
            if holder is not None or e.status == 409 or "held" in str(e).lower():
                return False  # lease still alive: not ours yet
            raise
        self.role_room = room
        if self.watcher and (conn := self.watcher.connections.get(room.id)):
            conn.role_lost = False
        await self._announce_transfer(room, holder)
        return True

    async def _announce_transfer(self, room: RoomInfo, previous: str | None) -> None:
        text = receipts.hands_now_on(self.name)
        targets = [room, *[r for r in self.hq_rooms() if r.id != room.id]]
        for r in targets:
            await self._safe_reply(r, text)
        self.bus.publish(TransferEvent(from_agent=previous or "desk-laptop", to_agent=self.name))
        self.bus.publish(SystemEvent(level="info", text=f"hands transferred to {self.name}"))
        self.actions.speak("Hands transferred to backup.")
        log.info("hands is now on %s (mission %s)", self.name, room.name)


async def run_backup(dry_run: bool = False, no_hud: bool = False) -> None:
    """`roomservice backup`: start the backup desk and idle until cancelled."""
    from roomservice.cli import _load_cfg, _status_table, console
    from roomservice.contracts.config import load_settings
    from roomservice.log import setup_logging

    setup_logging()
    settings = load_settings()
    dry = dry_run or settings.roomservice_dry_run
    agent = BackupAgent(cfg=_load_cfg(settings), settings=settings, dry_run=dry)
    await agent.start()
    hud_task: asyncio.Task | None = None
    if not no_hud:
        try:
            from roomservice.cli import _open_hud
            from roomservice.hud.server import run_hud

            hud_task = asyncio.create_task(run_hud(settings.hud_port), name="backup-hud")
            _open_hud(settings.hud_port)
        except Exception as e:
            console.print(f"[yellow]HUD failed to start: {e}[/yellow]")
    console.print(f"[green]backup up[/green] as {agent.name}{' (dry run)' if dry else ''}")
    try:
        while True:
            await asyncio.sleep(60)
            _status_table(agent)
    finally:
        if hud_task is not None:
            hud_task.cancel()
        with contextlib.suppress(Exception):
            await agent.stop()
