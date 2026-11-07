"""Full desk flow (SPEC §20.3): `@hands boot volt` (dry) -> receipts in order + HUD events.
Real DeskAgent + RoomWatcher + SwitchHTTPClient against the fake Switch; no OS calls."""

import asyncio
import re
import time

from roomservice import store
from roomservice.agents.desk import DeskAgent, add_owner
from roomservice.bus import Bus
from roomservice.contracts.config import Settings, load_desk_config
from roomservice.desk.os.dry import DryAdapter
from tests.contract.fake_switch import FakeSwitch, message_frame, sleep


async def wait_for(cond, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


def bodies(fake):
    return [c["args"]["body"] for c in fake.calls_named("op:post_message")]


async def test_boot_status_help_freeze_flow(fixtures_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    scripts = [
        [
            message_frame(1, "@hands boot volt"),
            sleep(0.5),
            message_frame(2, "@hands status"),
            message_frame(3, "@hands help"),
            sleep(0.5),
            message_frame(4, "@hands freeze"),
            message_frame(5, "@hands open browser"),
            message_frame(6, "@hands unfreeze"),
            sleep(0.3),
            message_frame(7, "@hands mission volt-waitlist volt"),
        ]
    ]
    fake = await FakeSwitch(scripts).start()
    monkeypatch.setenv("SWITCH_URL", fake.url)
    store.save_agent_creds(fake.url, "desk-laptop", "id-desk-laptop", "key-desk-laptop")
    add_owner("@owner:srv", "owner", "roomservice-hq")
    bus = Bus()
    events: list = []

    async def collect():
        async for ev in bus.subscribe():
            events.append(ev)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)
    agent = DeskAgent(
        cfg=load_desk_config(fixtures_dir / "desk_example.yaml"),
        settings=Settings(),
        adapter=DryAdapter(delay_s=0.01),
        bus=bus,
    )
    try:
        await agent.start()
        await wait_for(lambda: any(b.startswith("✅ task") for b in bodies(fake)))
        got = bodies(fake)

        boot = next(i for i, b in enumerate(got) if b.startswith("✅ boot volt"))
        assert re.fullmatch(
            r"✅ boot volt · editor, 1 terminal, 2 tabs, focus, music · \d+\.\ds", got[boot]
        )
        order = [
            next(i for i, b in enumerate(got) if b.startswith(p))
            for p in ("✅ boot", "✅ status", "🧊 paused by owner", "⛔ refused · paused by owner")
        ]
        assert order == sorted(order)
        assert any("boot <project>" in b for b in got)  # help
        assert "▶ resumed by owner" in got
        assert "✅ task volt-waitlist · already booted · computer assumed" in got

        # mission: assume_role(hands) bound to the room connection
        assume = fake.calls_named("op:assume_role")
        assert assume and assume[0]["args"] == {"role": "hands"} and assume[0]["conn_id"]

        types = [e.type for e in events]
        assert "action_start" in types and "action_end" in types
        assert "ignition" in types  # boot lights -> HUD flash
        assert "mission" in types and "freeze" in types and "speak" in types
        start = next(e for e in events if e.type == "action_start")
        assert (start.verb, start.args) == ("boot", ["volt"])
        end = next(e for e in events if e.type == "action_end")
        assert end.ok and end.ms >= 0
    finally:
        await agent.stop()
        collector.cancel()
        await fake.stop()


async def test_bus_on_freeze_is_wired(fixtures_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake = await FakeSwitch([[]]).start()
    monkeypatch.setenv("SWITCH_URL", fake.url)
    store.save_agent_creds(fake.url, "desk-laptop", "id-desk-laptop", "key-desk-laptop")
    bus = Bus()
    agent = DeskAgent(
        cfg=load_desk_config(fixtures_dir / "desk_example.yaml"),
        settings=Settings(),
        adapter=DryAdapter(delay_s=0),
        bus=bus,
    )
    try:
        await agent.start()
        assert bus.on_freeze is not None
        await bus.on_freeze(True)
        assert agent.frozen
        await bus.on_freeze(False)
        assert not agent.frozen
    finally:
        await agent.stop()
        await fake.stop()
