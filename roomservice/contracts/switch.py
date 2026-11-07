"""Frozen contract (SPEC §8.3): Switch frame/event models and the SwitchHTTP protocol."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel


class DomainEvent(BaseModel):
    """`data` of {"event": ..., "data": {...}, "id": n}."""

    type: Literal["message", "command", "room_join"]
    room_id: str
    bridge_id: str | None = None
    channel_type: str | None = None
    payload: dict
    sequence: int


class MessagePayload(BaseModel):
    addressed: bool
    sender: str
    sender_name: str
    message_id: str
    body: str
    timestamp: int
    thread_id: str | None = None
    attachments: list[dict] = []


class OpError(Exception):
    status: int
    detail: str

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class SwitchHTTP(Protocol):
    async def health(self) -> bool: ...

    async def register(
        self,
        name: str,
        display_name: str,
        description: str,
        connector_type: str,
        overwrite: bool = False,
    ) -> tuple[str, str]:  # (id, api_key)
        ...

    async def list_ops(self) -> dict: ...

    async def op(self, name: str, args: dict, conn_id: str | None = None) -> Any:
        """Drops None values from args."""
        ...

    async def post(self, room_id: str, content: str) -> str:  # event_id
        ...

    async def upload(
        self,
        room_id: str,
        files: list[tuple[str, bytes, str]],
        caption: str | None = None,
        thread_id: str | None = None,
    ) -> dict: ...

    async def typing(self, room_id: str, on: bool) -> None:  # never raises
        ...

    async def renew_lease(self, conn_id: str) -> bool: ...
