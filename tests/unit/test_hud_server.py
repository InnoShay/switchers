import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from roomservice import store
from roomservice.bus import bus
from roomservice.contracts.events import SpeakEvent
from roomservice.hud import server

VALID = "shot-volt-143201.png"
EVIL = {"Origin": "http://evil.example"}


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def local(monkeypatch):
    """TestClient reports its peer as 'testclient'; treat that as loopback."""
    monkeypatch.setattr(server, "LOOPBACK", server.LOOPBACK | {"testclient"})


@pytest.fixture
def freeze_rec():
    saved = bus.on_freeze
    calls: list[bool] = []

    async def rec(on: bool) -> None:
        calls.append(on)

    bus.on_freeze = rec
    yield calls
    bus.on_freeze = saved


def test_index_and_static(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert client.get("/static/hud.js").status_code == 200
    assert client.get("/static/hud.css").status_code == 200


def test_state_is_hello(client):
    body = client.get("/api/state").json()
    assert body["type"] == "hello"
    assert len(body["crew"]) == 6


def test_shot_served_from_tmp_home(client):
    path = store.shots_dir() / VALID
    assert "rs-home" in str(path)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    r = client.get(f"/shots/{VALID}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


@pytest.mark.parametrize(
    "name", ["..%2Fx.png", "../x.png", "shot-VOLT-143201.png", "foo.png", VALID]
)
def test_shot_invalid_or_missing_is_404(client, name):
    assert client.get(f"/shots/{name}").status_code == 404


def test_freeze_ok(client, local, freeze_rec):
    r = client.post("/api/freeze", json={"on": True})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "on": True}
    assert freeze_rec == [True]


@pytest.mark.parametrize("payload", [{"on": "yes"}, {"on": 1}, [True], {}])
def test_freeze_non_bool_400(client, local, freeze_rec, payload):
    assert client.post("/api/freeze", json=payload).status_code == 400
    assert freeze_rec == []


def test_freeze_non_json_400(client, local, freeze_rec):
    r = client.post("/api/freeze", content=b"not json", headers={"content-type": "text/plain"})
    assert r.status_code == 400


def test_freeze_no_desk_503(client, local):
    saved = bus.on_freeze
    bus.on_freeze = None
    try:
        assert client.post("/api/freeze", json={"on": True}).status_code == 503
    finally:
        bus.on_freeze = saved


def test_freeze_evil_origin_403(client, local, freeze_rec):
    r = client.post("/api/freeze", json={"on": True}, headers=EVIL)
    assert r.status_code == 403
    assert freeze_rec == []


def test_freeze_non_loopback_client_403(client, freeze_rec):
    # no LOOPBACK patch: TestClient's peer is "testclient"
    assert client.post("/api/freeze", json={"on": True}).status_code == 403
    assert freeze_rec == []


def test_ws_hello_then_speak(client, local):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        deadline = time.monotonic() + 3
        while not bus._subs and time.monotonic() < deadline:
            time.sleep(0.01)
        assert bus._subs
        client.portal.call(bus.publish, SpeakEvent(text="hi there"))
        msg = ws.receive_json()
        assert msg["type"] == "speak"
        assert msg["text"] == "hi there"
        # Starlette's TestClient cancels the app right after the client closes, so let the
        # handler finish its cleanup first: close, wait for the subscriber to unregister.
        ws.close()
        deadline = time.monotonic() + 3
        while bus._subs and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not bus._subs
        time.sleep(0.1)


def test_ws_evil_origin_rejected(client, local):
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect("/ws", headers=EVIL) as ws:
            ws.receive_json()
    assert ei.value.code == 4403


def test_ws_non_loopback_rejected(client):
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
    assert ei.value.code == 4403
