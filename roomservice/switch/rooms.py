"""Room discovery (SPEC §11.5): poll list_rooms, keep one RoomConnection per room."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from roomservice.bus import bus as default_bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.events import SystemEvent
from roomservice.contracts.switch import SwitchHTTP
from roomservice.log import get_logger
from roomservice.switch.connection import ConnectedHook, EventHandler, RoomConnection

log = get_logger("switch.rooms")

POLL_INTERVAL_S = 3.0
MAX_CONNECTIONS = 30
_ACTIVITY_KEYS = (
    "last_activity",
    "last_activity_at",
    "last_message_at",
    "updated_at",
    "created_at",
)


def detect_kind(room_id: str, name: str, hq_rooms: list[str]) -> RoomKind:
    """hq if name or id is in ROOMSERVICE_HQ_ROOMS; mission if name starts with `mission-`."""
    hq = {h.strip().casefold() for h in hq_rooms}
    if room_id.casefold() in hq or name.strip().casefold() in hq:
        return RoomKind.HQ
    if name.casefold().startswith("mission-"):
        return RoomKind.MISSION
    return RoomKind.OTHER


def parse_rooms(result: Any) -> list[dict]:
    """Tolerant parse of the list_rooms result: a list, or a dict wrapping one."""
    if isinstance(result, dict):
        for key in ("rooms", "result", "items"):
            if isinstance(result.get(key), list):
                result = result[key]
                break
    if not isinstance(result, list):
        return []
    return [r for r in result if isinstance(r, dict) and (r.get("id") or r.get("room_id"))]


def _activity(raw: dict) -> float:
    for key in _ACTIVITY_KEYS:
        v = raw.get(key)
        if isinstance(v, int | float):
            return float(v)
        if isinstance(v, str) and v:
            return _iso_to_float(v)
    return 0.0


def _iso_to_float(v: str) -> float:
    from datetime import datetime

    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def select_rooms(rooms: list[RoomInfo], activity: dict[str, float], cap: int) -> list[RoomInfo]:
    """All HQ rooms, then the most recently active missions, then others, up to `cap`."""
    hq = [r for r in rooms if r.kind == RoomKind.HQ]
    rest = [r for r in rooms if r.kind != RoomKind.HQ]
    rest.sort(key=lambda r: (r.kind != RoomKind.MISSION, -activity.get(r.id, 0.0)))
    return hq + rest[: max(0, cap - len(hq))]


class RoomWatcher:
    def __init__(
        self,
        http: SwitchHTTP,
        *,
        base_url: str,
        agent_id: str,
        api_key: str,
        hq_rooms: list[str],
        on_event: EventHandler,
        on_connected: ConnectedHook | None = None,
        poll_interval_s: float = POLL_INTERVAL_S,
        cap: int = MAX_CONNECTIONS,
        bus: Any = default_bus,
        connection_factory: Callable[..., RoomConnection] = RoomConnection,
        connection_kwargs: dict | None = None,
    ) -> None:
        self.http = http
        self.base_url = base_url
        self.agent_id = agent_id
        self.api_key = api_key
        self.hq_names = hq_rooms
        self.on_event = on_event
        self.on_connected = on_connected
        self.poll_interval_s = poll_interval_s
        self.cap = cap
        self.bus = bus
        self._factory = connection_factory
        self._conn_kwargs = connection_kwargs or {}
        self.connections: dict[str, RoomConnection] = {}
        self.known: dict[str, RoomInfo] = {}
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None

    # -- queries ------------------------------------------------------------------------

    def rooms(self) -> list[RoomInfo]:
        return [c.room for c in self.connections.values()]

    def hq_rooms(self) -> list[RoomInfo]:
        return [r for r in self.rooms() if r.kind == RoomKind.HQ]

    def room(self, room_id: str) -> RoomInfo | None:
        conn = self.connections.get(room_id)
        return conn.room if conn else None

    def any_connected(self) -> bool:
        return any(c.connected for c in self.connections.values())

    # -- lifecycle ----------------------------------------------------------------------

    async def start(self) -> None:
        await self.poll_once()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for conn in list(self.connections.values()):
            await conn.stop()
        self.connections.clear()
        self.bus.set_connection("switch", False)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval_s)
            await self.poll_once()

    # -- one poll -----------------------------------------------------------------------

    async def poll_once(self) -> None:
        try:
            result = await self.http.op("list_rooms", {})
        except Exception as e:
            self.last_error = str(e)
            log.warning("list_rooms failed: %s", e)
            self.bus.set_connection("switch", False)
            return
        self.last_error = None

        infos: list[RoomInfo] = []
        activity: dict[str, float] = {}
        for raw in parse_rooms(result):
            rid = str(raw.get("id") or raw.get("room_id"))
            name = str(raw.get("name") or raw.get("display_name") or rid)
            info = RoomInfo(id=rid, name=name, kind=detect_kind(rid, name, self.hq_names))
            infos.append(info)
            activity[rid] = _activity(raw)
        self.known = {r.id: r for r in infos}
        wanted = {r.id: r for r in select_rooms(infos, activity, self.cap)}

        # Close connections for rooms that are gone/out of the cap, and reap dead ones.
        for rid, conn in list(self.connections.items()):
            if rid not in wanted:
                await conn.stop()
                del self.connections[rid]
                self.bus.publish(SystemEvent(level="info", text=f"room closed: {conn.room.name}"))
            elif conn.done:
                if conn.fatal:
                    continue  # leave it parked: retrying a fatal error every 3 s helps nobody
                del self.connections[rid]

        for rid, info in wanted.items():
            if rid in self.connections:
                self.connections[rid].room.name = info.name
                continue
            conn = self._factory(
                base_url=self.base_url,
                agent_id=self.agent_id,
                api_key=self.api_key,
                http=self.http,
                room=info,
                on_event=self.on_event,
                on_connected=self.on_connected,
                bus=self.bus,
                **self._conn_kwargs,
            )
            self.connections[rid] = conn
            conn.start()
            log.info("room opened: %s", info.name, extra={"room": info.name, "event": "room"})
            self.bus.publish(SystemEvent(level="info", text=f"room opened: {info.name}"))

        self.bus.set_connection("switch", self.any_connected())
