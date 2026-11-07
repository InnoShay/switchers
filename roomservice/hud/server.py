"""Mission Control HUD server (SPEC §16.1). FastAPI on 127.0.0.1, reads the shared bus."""

from __future__ import annotations

import asyncio
import contextlib
import re
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from roomservice import store
from roomservice.bus import bus
from roomservice.contracts.events import dump_event

STATIC_DIR = Path(__file__).parent / "static"
SHOT_RE = re.compile(r"^shot-[a-z0-9-]+-\d{6}\.png$")
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _origin_ok(origin: str | None) -> bool:
    """Browsers send Origin on cross-site requests; only our own loopback page may call us."""
    if not origin:
        return True  # curl, tests, same-origin GET
    return (urlparse(origin).hostname or "") in LOOPBACK


def create_app() -> FastAPI:
    app = FastAPI(title="RoomService HUD", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/shots/{file}")
    async def shot(file: str) -> FileResponse:
        if not SHOT_RE.match(file):
            raise HTTPException(404)
        path = store.shots_dir() / file
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png")

    @app.get("/api/state")
    async def state() -> dict:
        return bus.snapshot().model_dump()

    @app.post("/api/freeze")
    async def freeze(request: Request) -> dict:
        host = request.client.host if request.client else ""
        if host not in LOOPBACK or not _origin_ok(request.headers.get("origin")):
            raise HTTPException(403, "loopback only")
        try:
            body = await request.json()
        except ValueError as e:
            raise HTTPException(400, "expected JSON") from e
        if not isinstance(body, dict) or not isinstance(body.get("on"), bool):
            raise HTTPException(400, 'expected {"on": true|false}')
        if bus.on_freeze is None:
            raise HTTPException(503, "desk is not running")
        await bus.on_freeze(body["on"])
        return {"ok": True, "on": body["on"]}

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        host = sock.client.host if sock.client else ""
        if host not in LOOPBACK or not _origin_ok(sock.headers.get("origin")):
            await sock.close(code=4403)
            return
        await sock.accept()
        await sock.send_text(dump_event(bus.snapshot()))

        async def pump() -> None:
            async for ev in bus.subscribe():
                await sock.send_text(dump_event(ev))

        async def drain() -> None:  # notice client disconnects; the HUD sends nothing
            while True:
                await sock.receive_text()

        tasks = [asyncio.create_task(pump()), asyncio.create_task(drain())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in tasks:
                t.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*tasks, return_exceptions=True)
            with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                await sock.close()

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


async def run_hud(port: int) -> None:
    """Serve the HUD inside the runtime's event loop (SPEC §24.2 RS-08)."""
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", ws="auto")
    )
    await server.serve()
