"""Frozen contract (SPEC §8.4): the protocol agent base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel

from roomservice.contracts.switch import DomainEvent, MessagePayload


class RoomKind(StrEnum):
    HQ = "hq"
    MISSION = "mission"
    OTHER = "other"


class RoomInfo(BaseModel):
    id: str
    name: str
    kind: RoomKind
    conn_id: str | None = None


class ProtocolAgent(ABC):
    name: str

    async def start(self) -> None:
        """Registration loaded, watcher started."""
        raise NotImplementedError

    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def on_message(self, room: RoomInfo, ev: DomainEvent, msg: MessagePayload) -> None: ...

    async def reply(self, room: RoomInfo, text: str, thread_id: str | None = None) -> None:
        raise NotImplementedError

    async def upload(
        self,
        room: RoomInfo,
        png: bytes,
        filename: str,
        caption: str,
        thread_id: str | None = None,
    ) -> None:
        raise NotImplementedError

    def hq_rooms(self) -> list[RoomInfo]:
        raise NotImplementedError
