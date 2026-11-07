"""LifeAgent (SPEC §14.3): calendar and email through the n8n `RoomService Life` webhook."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx

from roomservice import store
from roomservice.agents.base import BaseProtocolAgent
from roomservice.contracts.agent import RoomInfo
from roomservice.contracts.events import SystemEvent
from roomservice.contracts.switch import DomainEvent, MessagePayload
from roomservice.desk.receipts import IST
from roomservice.log import get_logger

log = get_logger("life")

N8N_TIMEOUT_S = 60.0
TZ = "Asia/Kolkata"
START_CMD = "docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d"
_MENTION_RE = re.compile(r"@\S+")


def active_mission_slug() -> str | None:
    """Active mission slug from ~/.roomservice/active.json (written by the desk), else None."""
    from roomservice.desk.state import StateManager

    d = store.read_json(StateManager.active_path(), None)
    slug = d.get("slug") if isinstance(d, dict) else None
    return slug if isinstance(slug, str) and slug else None


class LifeAgent(BaseProtocolAgent):
    name = "life"

    def __init__(
        self,
        *,
        mission_slug: Callable[[], str | None] = active_mission_slug,
        now: Callable[[], datetime] | None = None,
        client: httpx.AsyncClient | None = None,
        **kw: Any,
    ) -> None:
        super().__init__("life", **kw)
        self._mission_slug = mission_slug
        self._now = now or (lambda: datetime.now(IST))
        self._client = client

    @property
    def n8n_url(self) -> str:
        return str(self.settings.n8n_life_url)

    def down_line(self) -> str:
        return f"⛔ life · n8n not reachable at {self.n8n_url}. Start it: {START_CMD}"

    async def ask_n8n(self, text: str, sender_name: str, room_name: str, mode: str) -> str | None:
        """POST to n8n. Returns the reply text, or None when n8n is down or answers badly
        (bus flag n8n=False and a HUD `system` warn are set here)."""
        payload = {
            "text": text,
            "sender_name": sender_name,
            "room_name": room_name,
            "mission_slug": self._mission_slug(),
            "now_iso": self._now().isoformat(timespec="seconds"),
            "tz": TZ,
            "mode": mode,
        }
        headers = {"X-RoomService-Token": self.settings.n8n_life_token.get_secret_value()}
        client = self._client or httpx.AsyncClient(timeout=N8N_TIMEOUT_S)
        try:
            r = await client.post(
                self.n8n_url, json=payload, headers=headers, timeout=N8N_TIMEOUT_S
            )
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            reply = r.json()["reply"]
        except Exception as e:
            log.warning("n8n call failed: %s", type(e).__name__)
            self.bus.set_connection("n8n", False)
            self.bus.publish(SystemEvent(level="warn", text=f"n8n not reachable at {self.n8n_url}"))
            return None
        finally:
            if self._client is None:
                await client.aclose()
        self.bus.set_connection("n8n", True)
        return str(reply)

    async def on_message(self, room: RoomInfo, ev: DomainEvent, msg: MessagePayload) -> None:
        text = _MENTION_RE.sub("", msg.body).strip()
        self._publish_state("working")
        try:
            async with self.typing(room):
                reply = await self.ask_n8n(text, msg.sender_name, room.name, "ask")
            line = f"🗓️ {reply}" if reply is not None else self.down_line()
            await self.reply(room, line, msg.thread_id)
        finally:
            self._publish_state("idle")

    async def brief(self) -> None:
        """Morning brief (SPEC §14.4): n8n `mode:"brief"`, posted in every HQ room."""
        rooms = self.hq_rooms()
        self._publish_state("working")
        try:
            reply = await self.ask_n8n(
                "Give me my morning brief.", "scheduler", "roomservice-hq", "brief"
            )
            line = f"☀️ Morning brief\n{reply}" if reply is not None else self.down_line()
            for room in rooms:
                try:
                    await self.reply(room, line)
                except Exception as e:
                    log.warning("brief post failed in %s: %s", room.name, e)
        finally:
            self._publish_state("idle")
