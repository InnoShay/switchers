"""Contract tests (SPEC §20.3, first five) for RoomConnection against the fake Switch."""

from __future__ import annotations

import asyncio
import time

import pytest

from roomservice import store
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.switch import DomainEvent
from roomservice.switch.connection import RoomConnection
from roomservice.switch.http import SwitchHTTPClient
from tests.contract.fake_switch import FakeSwitch, close, message_frame, send, sleep

AGENT_ID = "agent-1"


class StubBus:
    def __init__(self) -> None:
        self.events: list = []

    def publish(self, ev) -> None:
        self.events.append(ev)

    def set_connection(self, name: str, ok: bool) -> None:
        pass


async def wait_for(cond, timeout: float = 5.0, step: float = 0.02) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        await asyncio.sleep(step)
    raise AssertionError("condition not met in time")


@pytest.fixture
async def make():
    """Factory: (scripts, handler) -> (fake, conn). Cleans everything up afterwards."""
    started: list = []

    async def _make(scripts, handler=None, **conn_kw):
        fake = await FakeSwitch(scripts).start()
        http = SwitchHTTPClient(fake.url, agent_id=AGENT_ID, api_key="k")
        handled: list[int] = []

        async def default_handler(room: RoomInfo, ev: DomainEvent) -> None:
            handled.append(ev.sequence)

        bus = StubBus()
        conn = RoomConnection(
            base_url=fake.url,
            agent_id=AGENT_ID,
            api_key="k",
            http=http,
            room=RoomInfo(id="room-1", name="roomservice-hq", kind=RoomKind.HQ),
            on_event=handler or default_handler,
            bus=bus,
            backoff=conn_kw.pop("backoff", (0.05,)),
            persist_debounce_s=0.05,
            **conn_kw,
        )
        started.append((fake, http, conn))
        conn.handled = handled  # type: ignore[attr-defined]
        conn.stub_bus = bus  # type: ignore[attr-defined]
        return fake, conn

    yield _make
    for fake, http, conn in started:
        await conn.stop()
        await http.aclose()
        await fake.stop()


async def test_pong_within_100ms_while_handler_runs_2s(make):
    done = asyncio.Event()

    async def slow(room, ev):
        await asyncio.sleep(2)
        done.set()

    fake, conn = await make([[message_frame(1)]], handler=slow)
    conn.start()
    await asyncio.wait_for(done.wait(), 5)

    # ~10 pings arrive during the 2 s handler; every pong must be prompt.
    assert len(fake.pongs) >= 8
    assert max(p["latency"] for p in fake.pongs) < 0.1
    # the connection_state arrived and connect_to_room ran with our connection id
    (ctr,) = fake.calls_named("op:connect_to_room")
    assert ctr["conn_id"] == conn.connection_id
    assert ctr["args"] == {"room_id": "room-1"}
    # auth header is sent as a Bearer on the WebSocket open
    assert fake.ws_opens[0]["has_bearer"] is True


async def test_resume_uses_start_from_and_generation_without_duplicates(make):
    scripts = [
        [message_frame(1), message_frame(2), sleep(0.3), close(1012)],
        # server re-sends 2 after resume (at-least-once) plus a new event 3
        [message_frame(2), message_frame(3)],
    ]
    fake, conn = await make(scripts)
    conn.start()
    await wait_for(lambda: conn.handled == [1, 2, 3])
    await asyncio.sleep(0.2)  # a duplicate would show up by now

    assert conn.handled == [1, 2, 3]
    first, second = fake.ws_opens[0]["query"], fake.ws_opens[1]["query"]
    assert first["start_from"] == "head" and "expected_generation" not in first
    assert second["start_from"] == "2"
    assert second["expected_generation"] == "7"
    assert second["connection_id"] == first["connection_id"] == conn.connection_id
    assert first["scope"] == "single" and first["rooms"] == "room-1"
    assert first["client"] == "roomservice"
    # connect_to_room after each (re)open
    assert len(fake.calls_named("op:connect_to_room")) == 2

    await conn.stop()
    saved = store.read_json(store.cursors_path())[AGENT_ID]["room-1"]
    assert saved == {"connection_id": conn.connection_id, "generation": 7, "cursor": 3}


async def test_taken_over_stops_permanently(make):
    scripts = [[send({"type": "evicted", "code": "taken_over", "reason": "other runtime"})]]
    fake, conn = await make(scripts)
    conn.start()
    await asyncio.wait_for(conn.wait_closed(), 5)
    await asyncio.sleep(0.3)  # no reconnect even after the backoff elapsed

    assert conn.fatal and conn.done
    assert len(fake.ws_opens) == 1
    errors = [e for e in conn.stub_bus.events if getattr(e, "level", None) == "error"]
    assert errors and "taken over" in errors[0].text


async def test_heartbeat_lapsed_reconnects(make):
    scripts = [[send({"event": "evicted", "code": "heartbeat_lapsed", "reason": "silence"})], []]
    fake, conn = await make(scripts)
    conn.start()
    await wait_for(lambda: len(fake.ws_opens) >= 2)

    assert not conn.fatal and not conn.done
    assert conn.evictions == ["heartbeat_lapsed"]
    await wait_for(lambda: conn.connected)  # second socket is healthy again


async def test_gap_triggers_read_context_before_next_event(make):
    order: list[str] = []

    async def handler(room, ev):
        order.append(f"handled:{ev.sequence}")

    scripts = [
        [
            message_frame(1),
            sleep(0.3),
            send({"type": "gap", "from_sequence": 2, "resumed_at": 10, "reason": "trimmed"}),
            sleep(0.1),
            message_frame(11),
        ]
    ]
    fake, conn = await make(scripts, handler=handler)
    conn.start()
    await wait_for(lambda: "handled:11" in order)

    reads = fake.calls_named("op:read_context")
    assert len(reads) == 1
    assert reads[0]["args"] == {"limit": 20}
    assert reads[0]["conn_id"] == conn.connection_id
    # read_context hit the server after event 1 was handled and before event 11 was
    read_t = reads[0]["t"]
    assert order == ["handled:1", "handled:11"]
    assert conn.cursor == 11
    assert read_t > 0
    # a second event after the gap does not trigger another read_context
    assert len(fake.calls_named("op:read_context")) == 1
