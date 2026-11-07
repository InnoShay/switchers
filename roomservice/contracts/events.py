"""Frozen contract (SPEC §8.2): HUD events, JSON over ws://127.0.0.1:7777/ws."""

from __future__ import annotations

import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator

CREW_COLORS: dict[str, str] = {
    "you": "#F5F7FA",
    "concierge": "#7C9CFF",
    "builder": "#FFB547",
    "scout": "#4FD1C5",
    "hands": "#FF5C7A",
    "life": "#9BE564",
}

AgentState = Literal["offline", "idle", "working", "needs_you"]


def now_ms() -> int:
    return int(time.time() * 1000)


class CrewMember(BaseModel):
    name: str
    color: str
    state: AgentState


class Connections(BaseModel):
    switch: bool = False
    n8n: bool = False


class _Base(BaseModel):
    ts: int = Field(default_factory=now_ms)  # epoch ms


class HelloEvent(_Base):
    type: Literal["hello"] = "hello"
    mission: str | None = None
    crew: list[CrewMember]
    connections: Connections
    machine: str


class IgnitionEvent(_Base):
    type: Literal["ignition"] = "ignition"
    project: str
    lights: Literal["webhook", "flash"]


class MissionEvent(_Base):
    type: Literal["mission"] = "mission"
    slug: str
    title: str | None = None
    started_at: int


class MessageEvent(_Base):
    type: Literal["message"] = "message"
    room: str
    room_kind: Literal["hq", "mission", "other"]
    sender_name: str
    agent: str  # crew key, "you" or "other"
    body: str  # at most 400 chars (longer input is truncated)
    addressed: bool

    @field_validator("body")
    @classmethod
    def _cap_body(cls, v: str) -> str:
        return v if len(v) <= 400 else v[:399] + "…"


class AgentStateEvent(_Base):
    type: Literal["agent_state"] = "agent_state"
    agent: str
    state: AgentState


class ActionStartEvent(_Base):
    type: Literal["action_start"] = "action_start"
    id: str
    verb: str
    args: list[str] = []
    room: str


class ActionEndEvent(_Base):
    type: Literal["action_end"] = "action_end"
    id: str
    ok: bool
    ms: int
    summary: str


class ApprovalOpenEvent(_Base):
    type: Literal["approval_open"] = "approval_open"
    code: str
    cmd: str
    expires_at: int


class ApprovalClosedEvent(_Base):
    type: Literal["approval_closed"] = "approval_closed"
    code: str
    result: Literal["ok", "no", "expired"]
    by: str | None = None


class ScreenshotEvent(_Base):
    type: Literal["screenshot"] = "screenshot"
    url: str  # e.g. /shots/shot-volt-143201.png
    caption: str


class SpeakEvent(_Base):
    type: Literal["speak"] = "speak"
    text: str


class TransferEvent(_Base):
    type: Literal["transfer"] = "transfer"
    from_agent: str
    to_agent: str


class FreezeEvent(_Base):
    type: Literal["freeze"] = "freeze"
    on: bool


class SystemEvent(_Base):
    type: Literal["system"] = "system"
    level: Literal["info", "warn", "error"]
    text: str


HudEvent = Annotated[
    HelloEvent
    | IgnitionEvent
    | MissionEvent
    | MessageEvent
    | AgentStateEvent
    | ActionStartEvent
    | ActionEndEvent
    | ApprovalOpenEvent
    | ApprovalClosedEvent
    | ScreenshotEvent
    | SpeakEvent
    | TransferEvent
    | FreezeEvent
    | SystemEvent,
    Field(discriminator="type"),
]

_adapter: TypeAdapter[HudEvent] = TypeAdapter(HudEvent)


def parse_event(data: str | bytes | dict) -> HudEvent:
    """Parse JSON text or a dict into the right event model."""
    if isinstance(data, dict):
        return _adapter.validate_python(data)
    return _adapter.validate_json(data)


def dump_event(ev: HudEvent) -> str:
    """Serialize an event to JSON text."""
    return _adapter.dump_json(ev).decode()
