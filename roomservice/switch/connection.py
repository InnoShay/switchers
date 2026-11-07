"""One agent-protocol WebSocket per room (SPEC §11.4)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlencode

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

from roomservice import __version__, store
from roomservice.bus import bus as default_bus
from roomservice.contracts.agent import RoomInfo
from roomservice.contracts.events import SystemEvent
from roomservice.contracts.switch import DomainEvent, SwitchHTTP
from roomservice.log import get_logger

log = get_logger("switch.connection")

BACKOFF: tuple[float, ...] = (0.5, 1, 2, 4, 8, 10)
HEALTHY_AFTER_S = 30.0
PERSIST_DEBOUNCE_S = 1.0
CLOSED_RETRY_DELAY_S = 5.0
DOMAIN_TYPES = {"message", "command", "room_join"}
RECONNECT_EVICTIONS = {"heartbeat_lapsed", "no_stream", "unfenced", "connection_error"}

EventHandler = Callable[[RoomInfo, DomainEvent], Awaitable[None]]
ConnectedHook = Callable[[RoomInfo, Any], Awaitable[None]]


def ws_url(base_url: str) -> str:
    base = str(base_url).rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :]
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :]
    return base


# -- cursor persistence (~/.roomservice/cursors.json) -----------------------------------


def load_cursor_entry(agent_id: str, room_id: str) -> dict:
    data = store.read_json(store.cursors_path(), {})
    return dict(data.get(agent_id, {}).get(room_id, {}))


def save_cursor_entry(agent_id: str, room_id: str, entry: dict) -> None:
    # Synchronous read-modify-write: safe across RoomConnections sharing one event loop.
    data = store.read_json(store.cursors_path(), {})
    data.setdefault(agent_id, {})[room_id] = entry
    store.write_json(store.cursors_path(), data)


class RoomConnection:
    """Keeps one WebSocket open to one room; hands domain events to `on_event` serially."""

    def __init__(
        self,
        *,
        base_url: str,
        agent_id: str,
        api_key: str,
        http: SwitchHTTP,
        room: RoomInfo,
        on_event: EventHandler,
        on_connected: ConnectedHook | None = None,
        bus: Any = default_bus,
        backoff: tuple[float, ...] = BACKOFF,
        jitter: float = 0.2,
        healthy_after_s: float = HEALTHY_AFTER_S,
        persist_debounce_s: float = PERSIST_DEBOUNCE_S,
        closed_retry_delay_s: float = CLOSED_RETRY_DELAY_S,
        open_timeout: float = 10,
    ) -> None:
        self.base_url = ws_url(base_url)
        self.agent_id = agent_id
        self._api_key = api_key
        self.http = http
        self.room = room
        self.on_event = on_event
        self.on_connected = on_connected
        self.bus = bus
        self._backoff = backoff
        self._jitter = jitter
        self._healthy_after_s = healthy_after_s
        self._persist_debounce_s = persist_debounce_s
        self._closed_retry_delay_s = closed_retry_delay_s
        self._open_timeout = open_timeout

        entry = load_cursor_entry(agent_id, room.id)
        self.connection_id: str = entry.get("connection_id") or str(uuid.uuid4())
        self.generation: int | None = entry.get("generation")
        self.cursor: int | None = entry.get("cursor")
        self.room.conn_id = self.connection_id

        self.room_info: Any = None  # result of connect_to_room (instructions, participants, roles)
        self.connected = False  # a connection_state frame was received on the live socket
        self.state_received = False  # ever received a connection_state
        self.role_lost = False
        self.fatal = False  # stopped for good (bad key, taken over, ...)
        self.stop_reason: str | None = None
        self.evictions: list[str] = []
        self.rooms_in_state: list[str] = []

        self._stop = False
        self._gap_pending = False
        self._last_enqueued = -1
        self._closed_retry_used = False
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._ready = asyncio.Event()
        self._ws: Any = None
        self._after_open_task: asyncio.Task | None = None
        self._run_task: asyncio.Task | None = None
        self._handler_task: asyncio.Task | None = None
        self._persist_handle: asyncio.TimerHandle | None = None
        self._dirty = False

    # -- lifecycle ----------------------------------------------------------------------

    @property
    def done(self) -> bool:
        return self._run_task is not None and self._run_task.done()

    def start(self) -> None:
        if self._run_task is None:
            self._handler_task = asyncio.create_task(self._handler_loop())
            self._run_task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop = True
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
        for task in (self._run_task, self._handler_task):
            if task is not None:
                task.cancel()
        for task in (self._run_task, self._handler_task):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._flush()

    async def wait_closed(self) -> None:
        if self._run_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._run_task

    def _fatal(self, reason: str, *, level: str = "error") -> None:
        self.fatal = True
        self._stop = True
        self.stop_reason = reason
        text = f"{self.room.name}: {reason}"
        log.error("connection stopped: %s", text, extra={"room": self.room.name})
        self.bus.publish(SystemEvent(level=level, text=text))

    # -- cursor persistence -------------------------------------------------------------

    def _entry(self) -> dict:
        return {
            "connection_id": self.connection_id,
            "generation": self.generation,
            "cursor": self.cursor,
        }

    def _flush(self) -> None:
        if self._persist_handle is not None:
            self._persist_handle.cancel()
            self._persist_handle = None
        if self._dirty:
            self._dirty = False
            try:
                save_cursor_entry(self.agent_id, self.room.id, self._entry())
            except OSError as e:
                log.warning("cursor persist failed: %s", e)

    def _persist(self, immediate: bool = False) -> None:
        self._dirty = True
        if immediate:
            self._flush()
        elif self._persist_handle is None:
            loop = asyncio.get_running_loop()
            self._persist_handle = loop.call_later(self._persist_debounce_s, self._flush)

    # -- main loop ----------------------------------------------------------------------

    def _url(self) -> str:
        params: dict[str, Any] = {
            "connection_id": self.connection_id,
            "scope": "single",
            "filter": "all",
            "rooms": self.room.id,
            "start_from": self.cursor if self.cursor is not None else "head",
        }
        if self.generation is not None:
            params["expected_generation"] = self.generation
        params["client"] = "roomservice"
        params["client_version"] = __version__
        return f"{self.base_url}/agents/{self.agent_id}/connection/ws?{urlencode(params)}"

    def _delay(self, attempt: int) -> float:
        base = self._backoff[min(attempt, len(self._backoff) - 1)]
        return base * random.uniform(1 - self._jitter, 1 + self._jitter)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        attempt = 0
        try:
            while not self._stop:
                opened = loop.time()
                outcome = await self._session()
                if self._stop or outcome == "stop":
                    break
                if loop.time() - opened >= self._healthy_after_s:
                    attempt = 0
                    self._closed_retry_used = False
                if outcome == "closed":
                    delay = self._closed_retry_delay_s
                else:
                    delay = self._delay(attempt)
                    attempt += 1
                log.info(
                    "reconnecting in %.1fs", delay, extra={"room": self.room.name, "event": "retry"}
                )
                await asyncio.sleep(delay)
        finally:
            self.connected = False
            self._flush()

    async def _session(self) -> str:
        """One socket lifetime. Returns "reconnect", "closed" or "stop"."""
        self._ready.clear()
        self.connected = False
        self._after_open_task = None
        try:
            async with connect(
                self._url(),
                additional_headers={"Authorization": f"Bearer {self._api_key}"},
                open_timeout=self._open_timeout,
                ping_interval=None,
                max_size=8 * 2**20,
            ) as ws:
                self._ws = ws
                try:
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            continue
                        try:
                            frame = json.loads(raw)
                        except ValueError:
                            continue
                        if not isinstance(frame, dict):
                            continue
                        action = await self._on_frame(ws, frame)
                        if action:
                            return action
                except ConnectionClosed:
                    pass
                finally:
                    if self._after_open_task is not None:
                        self._after_open_task.cancel()
                    self._ws = None
                    self.connected = False
                return self._on_closed(ws.close_code, ws.close_reason or "")
        except InvalidStatus as e:
            status = e.response.status_code
            if status in (401, 403, 404):
                self._fatal(f"handshake refused ({status}); check the agent key and room access")
                return "stop"
            log.warning("handshake failed (%s)", status, extra={"room": self.room.name})
            return "reconnect"
        except (OSError, TimeoutError, WebSocketException) as e:
            log.warning("connect failed: %s", e, extra={"room": self.room.name})
            return "reconnect"

    def _on_closed(self, code: int | None, reason: str) -> str:
        log.info("socket closed code=%s reason=%s", code, reason, extra={"room": self.room.name})
        if code == 4401:
            self._fatal("auth failed (4401): the agent key is bad; run `roomservice register`")
            return "stop"
        if code == 4409 and "lapse" not in reason.lower():
            self._fatal(f"connection refused (4409): {reason or 'taken over or claimed'}")
            return "stop"
        if code == 4403:
            self._fatal("room cannot be served (4403): is the agent a member of this room?")
            return "stop"
        if code == 4400:
            self._fatal(f"bad connection parameters (4400): {reason}")
            return "stop"
        return "reconnect"  # 1000 / 1011 / 1012 / abnormal / 4409 with a lapse

    # -- frames -------------------------------------------------------------------------

    async def _on_frame(self, ws: Any, frame: dict) -> str | None:
        kind = frame.get("type") or frame.get("event")
        if kind == "ping":  # first, before anything else
            await ws.send(json.dumps({"type": "pong", "cursor": self.cursor or 0}))
            return None
        body = frame.get("data") if isinstance(frame.get("data"), dict) else frame

        if kind == "connection_state":
            self._on_state(body)
            return None
        if kind in DOMAIN_TYPES and "id" in frame:
            self._on_domain(frame)
            return None
        if kind == "gap":
            resumed = body.get("resumed_at")
            if isinstance(resumed, int):
                self.cursor = resumed
                self._last_enqueued = max(self._last_enqueued, resumed)
            self._gap_pending = True
            self._persist()
            log.warning("gap: %s", body.get("reason"), extra={"room": self.room.name})
            return None
        if kind == "evicted":
            return self._on_evicted(body)
        if kind == "subscription_changed":
            if self.room.id not in (body.get("rooms") or []):
                log.warning("room dropped from subscription", extra={"room": self.room.name})
                self.stop_reason = "subscription_changed"
                self._stop = True
                return "stop"
            return None
        if kind == "room_released":
            self.role_lost = True
            self.bus.publish(SystemEvent(level="warn", text=f"role lost in {self.room.name}"))
            return None
        if kind == "refused":
            status, detail = body.get("status"), body.get("detail")
            log.error("refused: %s %s", status, detail, extra={"room": self.room.name})
            if isinstance(status, int) and 400 <= status < 500 and status not in (408, 429):
                self._fatal(f"refused ({status}): {detail}")
                return "stop"
            return "reconnect"
        return None

    def _on_state(self, body: dict) -> None:
        if isinstance(body.get("generation"), int):
            self.generation = body["generation"]
        if self.cursor is None and isinstance(body.get("cursor"), int):
            self.cursor = body["cursor"]  # fresh start from head
        self.rooms_in_state = list(body.get("rooms") or [])
        self.state_received = True
        self.connected = True
        self._persist(immediate=True)
        if self._after_open_task is None:
            self._after_open_task = asyncio.create_task(self._after_open())

    def _on_domain(self, frame: dict) -> None:
        seq = frame["id"]
        if not isinstance(seq, int) or seq <= max(self.cursor if self.cursor is not None else -1,
                                                   self._last_enqueued):  # fmt: skip
            return
        data = dict(frame.get("data") or {})
        data.setdefault("type", frame.get("event"))
        data.setdefault("sequence", seq)
        data.setdefault("room_id", self.room.id)
        data.setdefault("payload", {})
        try:
            ev = DomainEvent.model_validate(data)
        except ValueError as e:
            log.warning("bad domain frame: %s", e, extra={"room": self.room.name})
            return
        self._last_enqueued = seq
        self._queue.put_nowait((seq, ev))

    def _on_evicted(self, body: dict) -> str | None:
        code = str(body.get("code") or "")
        reason = body.get("reason")
        self.evictions.append(code)
        log.warning("evicted %s %s", code, reason, extra={"room": self.room.name})
        if code == "taken_over":
            self._fatal("taken over by another connection; this runtime stopped")
            return "stop"
        if code in RECONNECT_EVICTIONS:
            return "reconnect"
        if code == "closed":
            if self._closed_retry_used:
                self._fatal(f"connection closed by server: {reason}", level="warn")
                return "stop"
            self._closed_retry_used = True
            return "closed"
        return "reconnect"

    # -- connect_to_room ----------------------------------------------------------------

    async def _after_open(self) -> None:
        try:
            self.room_info = await self.http.op(
                "connect_to_room", {"room_id": self.room.id}, self.connection_id
            )
            if self.on_connected is not None:
                await self.on_connected(self.room, self.room_info)
        except Exception as e:
            log.warning("connect_to_room failed: %s", e, extra={"room": self.room.name})
        finally:
            self._ready.set()

    # -- handler ------------------------------------------------------------------------

    async def _handler_loop(self) -> None:
        while True:
            item = await self._queue.get()
            seq, ev = item
            await self._ready.wait()
            if self._gap_pending:
                self._gap_pending = False
                try:
                    ctx = await self.http.op("read_context", {"limit": 20}, self.connection_id)
                    log.info("gap context: %s", str(ctx)[:200], extra={"room": self.room.name})
                except Exception as e:
                    log.warning("read_context failed: %s", e, extra={"room": self.room.name})
            try:
                await self.on_event(self.room, ev)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("handler failed: %s", e, extra={"room": self.room.name})
            if self.cursor is None or seq > self.cursor:
                self.cursor = seq
            self._persist()
