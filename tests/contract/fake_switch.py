"""In-process fake Switch server (SPEC §20.3): FastAPI HTTP + WebSocket, records every call.

Usage:
    fake = FakeSwitch(scripts=[[state_and_frames...], [...]])
    await fake.start()          # fake.url == "http://127.0.0.1:<port>"
    ...
    await fake.stop()

`scripts[i]` drives the i-th WebSocket connection. A script is a list of steps:
    {"send": {...}}     send a JSON frame
    {"sleep": 0.2}      wait
    {"close": 1012}     close the socket with that code
After the script ends the socket stays open (pings keep flowing) until the client leaves.
Every connection starts with a `connection_state` frame and gets a `ping` every `ping_every`.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse


def send(frame: dict) -> dict:
    return {"send": frame}


def sleep(seconds: float) -> dict:
    return {"sleep": seconds}


def close(code: int) -> dict:
    return {"close": code}


def message_frame(seq: int, body: str = "hi", *, addressed: bool = True, room_id: str = "room-1"):
    """A scripted domain frame: {"event": "message", "data": {...}, "id": seq}."""
    return send(
        {
            "event": "message",
            "id": seq,
            "data": {
                "type": "message",
                "room_id": room_id,
                "sequence": seq,
                "payload": {
                    "addressed": addressed,
                    "sender": "@owner:srv",
                    "sender_name": "owner",
                    "message_id": f"m{seq}",
                    "body": body,
                    "timestamp": 1_700_000_000_000 + seq,
                },
            },
        }
    )


class FakeSwitch:
    def __init__(
        self,
        scripts: list[list[dict]] | None = None,
        *,
        ping_every: float = 0.2,
        generation: int = 7,
        rooms: list[dict] | None = None,
        lease_ttl: float | None = None,
    ) -> None:
        self.scripts = scripts or []
        self.ping_every = ping_every
        self.generation = generation
        self.rooms = rooms if rooms is not None else [{"id": "room-1", "name": "roomservice-hq"}]
        self.agents: dict[str, dict] = {}
        # Role state (assume/release/list_roles): role -> {"agent_id", "name", "renewed"}.
        # With `lease_ttl`, a holder that stopped renewing for that long loses the role.
        self.roles: dict[str, dict] = {}
        self.lease_ttl = lease_ttl
        self.calls: list[dict] = []  # every HTTP/WS interaction, in order
        self.ws_opens: list[dict] = []  # query params + headers of each WebSocket open
        self.pongs: list[dict] = []  # {"cursor", "latency", "t"}
        self.url = ""
        self.app = self._build()
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None

    # -- recording helpers --------------------------------------------------------------

    def _rec(self, name: str, **kw: Any) -> dict:
        rec = {"name": name, "t": time.monotonic(), **kw}
        self.calls.append(rec)
        return rec

    def _holder(self, role: str) -> dict | None:
        cur = self.roles.get(role)
        if (
            cur
            and self.lease_ttl is not None
            and time.monotonic() - cur["renewed"] > self.lease_ttl
        ):
            del self.roles[role]  # lease lapsed
            return None
        return cur

    def _agent_name(self, agent_id: str) -> str:
        return next((n for n, a in self.agents.items() if a["id"] == agent_id), agent_id)

    def calls_named(self, name: str) -> list[dict]:
        return [c for c in self.calls if c["name"] == name]

    # -- server lifecycle ---------------------------------------------------------------

    async def start(self) -> FakeSwitch:
        config = uvicorn.Config(
            self.app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            await asyncio.sleep(0.01)
        port = self._server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task

    # -- app ----------------------------------------------------------------------------

    def _build(self) -> FastAPI:
        app = FastAPI()
        fake = self

        def authed(request: Request) -> bool:
            return request.headers.get("authorization", "").startswith("Bearer ")

        @app.get("/health")
        async def health():
            fake._rec("health")
            return {"status": "ok"}

        @app.post("/agents")
        async def register(request: Request):
            body = await request.json()
            fake._rec("register", body=body, auth=authed(request))
            name = body["name"]
            if name in fake.agents and not body.get("overwrite"):
                return JSONResponse({"detail": "exists"}, status_code=409)
            agent = {"id": f"id-{name}", "api_key": f"key-{name}"}
            fake.agents[name] = agent
            return agent

        @app.get("/agents/{agent_id}/ops")
        async def list_ops(agent_id: str, request: Request):
            fake._rec("list_ops", auth=authed(request))
            return {"operations": {"list_rooms": {}, "post_message": {}}}

        @app.post("/agents/{agent_id}/ops/{op_name}")
        async def op(agent_id: str, op_name: str, request: Request):
            args = await request.json() if await request.body() else {}
            conn_id = request.headers.get("x-switch-connection-id")
            fake._rec(f"op:{op_name}", args=args, conn_id=conn_id, auth=authed(request))
            if op_name == "list_rooms":
                return {"result": fake.rooms}
            if op_name == "connect_to_room":
                return {
                    "result": {
                        "instructions": "be nice",
                        "participants": [
                            {"id": "@self:srv", "name": "desk-laptop"},
                            {"id": "@owner:srv", "name": "owner"},
                        ],
                        "roles": [],
                    }
                }
            if op_name == "read_context":
                return {"result": {"messages": []}}
            if op_name == "list_roles":
                held = [(r, fake._holder(r)) for r in list(fake.roles)]
                return {"result": [{"name": r, "holder": h["name"]} for r, h in held if h]}
            if op_name == "assume_role":
                role = args["role"]
                cur = fake._holder(role)
                if cur and cur["agent_id"] != agent_id:
                    return JSONResponse(
                        {"detail": f"role {role} is held by {cur['name']}"}, status_code=409
                    )
                fake.roles[role] = {
                    "agent_id": agent_id,
                    "name": fake._agent_name(agent_id),
                    "renewed": time.monotonic(),
                }
                return {"result": {"ok": True}}
            if op_name == "release_role":
                for r in [r for r, h in fake.roles.items() if h["agent_id"] == agent_id]:
                    del fake.roles[r]
                return {"result": {"ok": True}}
            return {"result": {"ok": True}}

        @app.post("/agents/{agent_id}/message")
        async def message(agent_id: str, request: Request):
            body = await request.json()
            fake._rec("message", body=body, auth=authed(request))
            return {"ok": True, "event_id": "evt-1"}

        @app.post("/agents/{agent_id}/rooms/{room_id}/media")
        async def media(
            agent_id: str,
            room_id: str,
            request: Request,
            file: Annotated[UploadFile | None, File()] = None,
            caption: Annotated[str | None, Form()] = None,
            thread_id: Annotated[str | None, Form()] = None,
        ):
            data = await file.read() if file else b""
            fake._rec(
                "media",
                room_id=room_id,
                filename=file.filename if file else None,
                size=len(data),
                content_type=file.content_type if file else None,
                caption=caption,
                thread_id=thread_id,
                auth=authed(request),
            )
            return {"ok": True, "event_id": "evt-media"}

        @app.post("/agents/{agent_id}/typing")
        async def typing(agent_id: str, request: Request):
            fake._rec("typing", body=await request.json())
            return {"ok": True}

        @app.post("/agents/{agent_id}/leases/renew")
        async def lease(agent_id: str, request: Request):
            fake._rec(
                "lease_renew",
                agent_id=agent_id,
                conn_id=request.headers.get("x-switch-connection-id"),
            )
            for h in fake.roles.values():
                if h["agent_id"] == agent_id:
                    h["renewed"] = time.monotonic()
            return {"ok": True}

        @app.websocket("/agents/{agent_id}/connection/ws")
        async def ws_endpoint(ws: WebSocket, agent_id: str):
            await ws.accept()
            idx = len(fake.ws_opens)
            q = dict(ws.query_params)
            fake.ws_opens.append(
                {
                    "query": q,
                    "has_bearer": ws.headers.get("authorization", "").startswith("Bearer "),
                }
            )
            fake._rec("ws_open", query=q)
            script = fake.scripts[idx] if idx < len(fake.scripts) else []
            await fake._serve_ws(ws, agent_id, q, script)

        return app

    async def _serve_ws(self, ws: WebSocket, agent_id: str, q: dict, script: list[dict]) -> None:
        start = q.get("start_from", "head")
        cursor = int(start) if start.isdigit() else 0
        await ws.send_json(
            {
                "type": "connection_state",
                "connection_id": q.get("connection_id"),
                "agent_id": agent_id,
                "generation": self.generation,
                "cursor": cursor,
                "rooms": (q.get("rooms") or "").split(","),
                "heartbeat_interval_seconds": 2,
            }
        )
        outstanding: list[float] = []

        async def pinger() -> None:
            while True:
                await asyncio.sleep(self.ping_every)
                outstanding.append(time.monotonic())
                await ws.send_json({"type": "ping"})

        async def reader() -> None:
            try:
                while True:
                    raw = await ws.receive_text()
                    now = time.monotonic()
                    frame = json.loads(raw)
                    if frame.get("type") == "pong":
                        sent = outstanding.pop(0) if outstanding else now
                        self.pongs.append(
                            {"cursor": frame.get("cursor"), "latency": now - sent, "t": now}
                        )
            except (WebSocketDisconnect, RuntimeError):
                return

        tasks = [asyncio.create_task(pinger()), asyncio.create_task(reader())]
        try:
            for step in script:
                if "send" in step:
                    await ws.send_json(step["send"])
                elif "sleep" in step:
                    await asyncio.sleep(step["sleep"])
                elif "close" in step:
                    await ws.close(code=step["close"])
                    return
            await tasks[1]  # idle until the client disconnects
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            for t in tasks:
                t.cancel()
