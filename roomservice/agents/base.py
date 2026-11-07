"""BaseProtocolAgent (SPEC §11.6, §11.7): connection plumbing shared by every runtime agent."""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections import OrderedDict
from collections.abc import AsyncIterator
from typing import Any

from roomservice import store
from roomservice.bus import bus as default_bus
from roomservice.contracts.agent import ProtocolAgent, RoomInfo
from roomservice.contracts.config import Settings, load_settings
from roomservice.contracts.events import AgentStateEvent, MessageEvent
from roomservice.contracts.switch import DomainEvent, MessagePayload, OpError, SwitchHTTP
from roomservice.log import get_logger
from roomservice.switch.http import SwitchHTTPClient
from roomservice.switch.rooms import RoomWatcher

log = get_logger("agent")

DEDUPE_SIZE = 2000
MAX_BODY = 3500
TYPING_AFTER_S = 0.3
CREW_KEYS = {"concierge", "builder", "scout", "hands", "life"}
CREW_ALIASES = {"desk": "hands"}
AGENT_CREW_KEY = {"desk-laptop": "hands", "desk-backup": "hands", "life": "life"}
REGISTER_HINT = "Run `uv run roomservice register` first"


def truncate_body(text: str, limit: int = MAX_BODY) -> str:
    """Telegram/Mattermost length guard: cap at 3,500 chars + an ellipsis."""
    return text if len(text) <= limit else text[:limit] + "…"


def _collect_senders(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "sender" and isinstance(v, str):
                out.add(v)
            else:
                _collect_senders(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_senders(v, out)


def owner_ids() -> set[str]:
    """Paired owner participant ids from ~/.roomservice/owners.json (written by RS-07 pairing)."""
    out: set[str] = set()
    _collect_senders(store.read_json(store.owners_path(), {}), out)
    return out


def resolve_agent_key(sender_name: str, sender: str) -> str:
    """HUD `agent` field: crew key, "you" (paired owner) or "other"."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", sender_name.casefold()) if t]
    for t in tokens:
        if t in CREW_KEYS:
            return t
        if t in CREW_ALIASES:
            return CREW_ALIASES[t]
    if sender in owner_ids():
        return "you"
    return "other"


def find_self_id(room_info: Any, name: str) -> str | None:
    """The participant whose name equals our agent name (from connect_to_room)."""
    participants = room_info.get("participants") if isinstance(room_info, dict) else None
    if not isinstance(participants, list):
        return None
    for p in participants:
        if not isinstance(p, dict):
            continue
        if name in (p.get("name"), p.get("agent_name"), p.get("display_name")):
            for key in ("id", "participant_id", "user_id", "sender"):
                if p.get(key):
                    return str(p[key])
    return None


class BaseProtocolAgent(ProtocolAgent):
    name: str = ""

    def __init__(
        self,
        name: str | None = None,
        *,
        settings: Settings | None = None,
        http: SwitchHTTP | None = None,
        bus: Any = default_bus,
        watcher_kwargs: dict | None = None,
    ) -> None:
        if name:
            self.name = name
        if not self.name:
            raise ValueError("agent needs a name")
        self.settings = settings or load_settings()
        self.bus = bus
        self.switch_url = str(self.settings.switch_url).rstrip("/")
        creds = store.load_agent_creds(self.switch_url, self.name)
        if not creds:
            raise SystemExit(f"No credentials for agent '{self.name}' on {self.switch_url}. "
                             f"{REGISTER_HINT}")  # fmt: skip
        self.agent_id: str = creds["id"]
        self._api_key: str = creds["api_key"]
        self.http: SwitchHTTP = http or SwitchHTTPClient(
            self.switch_url, agent_id=self.agent_id, api_key=self._api_key
        )
        self.self_id: str | None = None
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._watcher_kwargs = watcher_kwargs or {}
        self.watcher: RoomWatcher | None = None

    # -- lifecycle ----------------------------------------------------------------------

    async def start(self) -> None:
        self.watcher = RoomWatcher(
            self.http,
            base_url=self.switch_url,
            agent_id=self.agent_id,
            api_key=self._api_key,
            hq_rooms=self.settings.roomservice_hq_rooms,
            on_event=self._handle,
            on_connected=self._on_connected,
            bus=self.bus,
            **self._watcher_kwargs,
        )
        await self.watcher.start()
        self._publish_state("idle")

    async def stop(self) -> None:
        if self.watcher is not None:
            await self.watcher.stop()
        self._publish_state("offline")
        aclose = getattr(self.http, "aclose", None)
        if aclose is not None:
            await aclose()

    def _publish_state(self, state: str) -> None:
        key = AGENT_CREW_KEY.get(self.name)
        if key:
            self.bus.publish(AgentStateEvent(agent=key, state=state))  # type: ignore[arg-type]

    def hq_rooms(self) -> list[RoomInfo]:
        return self.watcher.hq_rooms() if self.watcher else []

    def rooms(self) -> list[RoomInfo]:
        return self.watcher.rooms() if self.watcher else []

    # -- inbound ------------------------------------------------------------------------

    async def _on_connected(self, room: RoomInfo, room_info: Any) -> None:
        found = find_self_id(room_info, self.name)
        if found:
            self.self_id = found

    def wants_unaddressed(self, room: RoomInfo, msg: MessagePayload) -> bool:
        """Subclasses return True to receive messages that were not addressed to them."""
        return False

    def _is_duplicate(self, message_id: str) -> bool:
        if message_id in self._seen:
            self._seen.move_to_end(message_id)
            return True
        self._seen[message_id] = None
        if len(self._seen) > DEDUPE_SIZE:
            self._seen.popitem(last=False)
        return False

    async def _handle(self, room: RoomInfo, ev: DomainEvent) -> None:
        if ev.type != "message":
            return
        try:
            msg = MessagePayload.model_validate(ev.payload)
        except ValueError as e:
            log.warning("bad message payload: %s", e, extra={"room": room.name})
            return
        if self._is_duplicate(msg.message_id):
            return
        self.bus.publish(
            MessageEvent(
                room=room.name,
                room_kind=room.kind.value,
                sender_name=msg.sender_name,
                agent=resolve_agent_key(msg.sender_name, msg.sender),
                body=msg.body,
                addressed=msg.addressed,
            )
        )
        if self.self_id is not None and msg.sender == self.self_id:
            return
        if not (msg.addressed or self.wants_unaddressed(room, msg)):
            return
        await self.on_message(room, ev, msg)

    # -- outbound -----------------------------------------------------------------------

    async def reply(self, room: RoomInfo, text: str, thread_id: str | None = None) -> None:
        text = truncate_body(text)
        if room.conn_id:
            try:
                await self.http.op(
                    "post_message", {"body": text, "thread_id": thread_id}, room.conn_id
                )
                return
            except OpError as e:
                if e.status != 409:
                    raise
                log.warning("post_message 409; falling back to post()", extra={"room": room.name})
        await self.http.post(room.id, text)

    async def upload(
        self,
        room: RoomInfo,
        png: bytes,
        filename: str,
        caption: str,
        thread_id: str | None = None,
    ) -> None:
        await self.http.upload(
            room.id, [(filename, png, "image/png")], truncate_body(caption), thread_id
        )

    @contextlib.asynccontextmanager
    async def typing(self, room: RoomInfo, after_s: float = TYPING_AFTER_S) -> AsyncIterator[None]:
        """Show "typing" only if the wrapped work takes longer than `after_s` (300 ms)."""
        shown = False

        async def _later() -> None:
            nonlocal shown
            await asyncio.sleep(after_s)
            shown = True
            await self.http.typing(room.id, True)

        task = asyncio.create_task(_later())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            if shown:
                await self.http.typing(room.id, False)
