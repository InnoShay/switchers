import asyncio

from roomservice.bus import QUEUE_SIZE, Bus
from roomservice.contracts.events import (
    AgentStateEvent,
    ApprovalClosedEvent,
    ApprovalOpenEvent,
    MissionEvent,
    SystemEvent,
)


async def _first(bus: Bus):
    async for ev in bus.subscribe():
        return ev


async def test_fan_out_to_all_subscribers():
    bus = Bus()
    t1 = asyncio.create_task(_first(bus))
    t2 = asyncio.create_task(_first(bus))
    await asyncio.sleep(0)
    bus.publish(SystemEvent(level="info", text="hi"))
    assert (await asyncio.wait_for(t1, 1)).text == "hi"
    assert (await asyncio.wait_for(t2, 1)).text == "hi"


async def test_overflow_drops_oldest():
    bus = Bus()
    got: list[str] = []
    ready = asyncio.Event()

    async def consume():
        agen = bus.subscribe()
        it = agen.__aiter__()
        first = asyncio.ensure_future(it.__anext__())
        await asyncio.sleep(0)
        ready.set()
        got.append((await first).text)
        await asyncio.sleep(0.05)
        for _ in range(3):
            got.append((await it.__anext__()).text)
        await agen.aclose()

    task = asyncio.create_task(consume())
    await ready.wait()
    bus.publish(SystemEvent(level="info", text="first"))
    await asyncio.sleep(0.01)
    # The consumer now sleeps; overflow its queue.
    for i in range(QUEUE_SIZE + 3):
        bus.publish(SystemEvent(level="info", text=str(i)))
    await asyncio.wait_for(task, 2)
    assert got[0] == "first"
    assert got[1:] == [str(i) for i in (3, 4, 5)]  # oldest 3 were dropped


async def test_unsubscribe_cleans_up():
    bus = Bus()
    agen = bus.subscribe()
    task = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)
    assert len(bus._subs) == 1
    bus.publish(SystemEvent(level="info", text="x"))
    await task
    await agen.aclose()
    assert len(bus._subs) == 0


def test_snapshot_tracks_events():
    bus = Bus()
    snap = bus.snapshot()
    assert [m.name for m in snap.crew] == [
        "you", "concierge", "builder", "scout", "hands", "life",
    ]  # fmt: skip
    assert snap.mission is None
    bus.set_machine("laptop")
    bus.set_connection("switch", True)
    bus.publish(MissionEvent(slug="volt-waitlist", started_at=1))
    bus.publish(AgentStateEvent(agent="builder", state="working"))
    bus.publish(ApprovalOpenEvent(code="K7Q3", cmd="commit", expires_at=2))
    snap = bus.snapshot()
    states = {m.name: m.state for m in snap.crew}
    assert snap.mission == "volt-waitlist"
    assert snap.machine == "laptop"
    assert snap.connections.switch is True and snap.connections.n8n is False
    assert states["builder"] == "working" and states["you"] == "needs_you"
    bus.publish(ApprovalClosedEvent(code="K7Q3", result="ok"))
    assert {m.name: m.state for m in bus.snapshot().crew}["you"] == "idle"


def test_module_singleton_and_on_freeze_default():
    from roomservice.bus import bus

    assert isinstance(bus, Bus)
    assert bus.on_freeze is None
