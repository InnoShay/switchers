"""HUD pub/sub (SPEC §8.2). One module-level singleton shared by runtime and HUD server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from roomservice.contracts.events import (
    CREW_COLORS,
    ActionEndEvent,
    ActionStartEvent,
    AgentStateEvent,
    ApprovalClosedEvent,
    ApprovalOpenEvent,
    Connections,
    CrewMember,
    HelloEvent,
    HudEvent,
    MissionEvent,
)

QUEUE_SIZE = 500
_CREW_ORDER = ["you", "concierge", "builder", "scout", "hands", "life"]


class Bus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[HudEvent]] = set()
        self._mission: str | None = None
        self._machine = "unknown"
        self._connections = Connections()
        self._states: dict[str, str] = dict.fromkeys(_CREW_ORDER, "offline")
        self.on_freeze: Callable[[bool], Awaitable[None]] | None = None

    # -- publish / subscribe ------------------------------------------------------------

    def publish(self, ev: HudEvent) -> None:
        """Fan out to every subscriber. Per-subscriber queue of 500; drops oldest on overflow."""
        self._apply(ev)
        for q in list(self._subs):
            while True:
                try:
                    q.put_nowait(ev)
                    break
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass

    async def subscribe(self) -> AsyncIterator[HudEvent]:
        """Async generator of events published after the first iteration step."""
        q: asyncio.Queue[HudEvent] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subs.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs.discard(q)

    # -- snapshot -----------------------------------------------------------------------

    def snapshot(self) -> HelloEvent:
        """Current mission, crew states, connections and machine, as a `hello` event."""
        crew = [
            CrewMember(name=k, color=CREW_COLORS[k], state=self._states[k])  # type: ignore[arg-type]
            for k in _CREW_ORDER
        ]
        return HelloEvent(
            mission=self._mission,
            crew=crew,
            connections=self._connections.model_copy(),
            machine=self._machine,
        )

    def set_connection(self, name: str, ok: bool) -> None:
        """Helper for the runtime: mark 'switch' or 'n8n' up/down in the snapshot."""
        if name in ("switch", "n8n"):
            setattr(self._connections, name, ok)

    def set_machine(self, machine: str) -> None:
        self._machine = machine

    def _apply(self, ev: HudEvent) -> None:
        if isinstance(ev, HelloEvent):
            self._mission = ev.mission
            self._machine = ev.machine
            self._connections = ev.connections.model_copy()
            for m in ev.crew:
                self._states[m.name] = m.state
        elif isinstance(ev, MissionEvent):
            self._mission = ev.slug
        elif isinstance(ev, AgentStateEvent):
            self._states[ev.agent] = ev.state
        elif isinstance(ev, ActionStartEvent):
            self._states["hands"] = "working"
        elif isinstance(ev, ActionEndEvent):
            self._states["hands"] = "idle"
        elif isinstance(ev, ApprovalOpenEvent):
            self._states["you"] = "needs_you"
        elif isinstance(ev, ApprovalClosedEvent):
            self._states["you"] = "idle"


bus = Bus()
