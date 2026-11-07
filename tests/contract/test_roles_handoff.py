"""Mission flow and desk-backup handoff against the fake Switch (SPEC §15, §20.3)."""

import asyncio
import time

from roomservice import store
from roomservice.agents.backup import BackupAgent
from roomservice.agents.desk import DeskAgent
from roomservice.bus import Bus
from roomservice.contracts.config import Settings, load_desk_config
from roomservice.desk.os.dry import DryAdapter
from tests.contract.fake_switch import FakeSwitch, message_frame, sleep

ROOMS = [
    {"id": "room-1", "name": "roomservice-hq"},
    {"id": "room-2", "name": "mission-a"},
    {"id": "room-3", "name": "mission-b"},
]


async def wait_for(cond, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


def bodies(fake, conn_id=None):
    return [
        c["args"]["body"]
        for c in fake.calls_named("op:post_message")
        if conn_id is None or c["conn_id"] == conn_id
    ]


def setup_fake(fake, monkeypatch, *names):
    monkeypatch.setenv("SWITCH_URL", fake.url)
    for n in names:
        store.save_agent_creds(fake.url, n, f"id-{n}", f"key-{n}")
        fake.agents[n] = {"id": f"id-{n}", "api_key": f"key-{n}"}


def make(cls, fixtures_dir, name, mode="lease", **kw):
    cfg = load_desk_config(fixtures_dir / "desk_example.yaml")
    if cls is BackupAgent:
        cfg = cfg.model_copy(update={"machine_name": "backup"})
    return cls(
        cfg=cfg,
        settings=Settings(roomservice_handoff_mode=mode),
        adapter=DryAdapter(delay_s=0.01),
        bus=Bus(),
        name=name,
        **kw,
    )


async def test_mission_flow_releases_old_assumes_new_and_renews(
    fixtures_dir, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    scripts = [
        [],  # HQ
        [message_frame(1, "@hands mission a none", room_id="room-2")],
        [sleep(1.0), message_frame(2, "@hands mission b none", room_id="room-3")],
    ]
    fake = await FakeSwitch(scripts, rooms=ROOMS).start()
    setup_fake(fake, monkeypatch, "desk-laptop")
    agent = make(DeskAgent, fixtures_dir, "desk-laptop")
    agent.lease_every_s = 0.2
    try:
        await agent.start()
        await wait_for(lambda: len(fake.calls_named("op:assume_role")) == 2)
        names = [
            c["name"] for c in fake.calls if c["name"] in ("op:assume_role", "op:release_role")
        ]
        assert names == ["op:assume_role", "op:release_role", "op:assume_role"]
        assume_a, assume_b = fake.calls_named("op:assume_role")
        release = fake.calls_named("op:release_role")[0]
        assert release["conn_id"] == assume_a["conn_id"] != assume_b["conn_id"]
        assert assume_b["args"] == {"role": "hands"}
        assert fake.roles["hands"]["name"] == "desk-laptop"

        await wait_for(
            lambda: (
                len(
                    [
                        c
                        for c in fake.calls_named("lease_renew")
                        if c["conn_id"] == assume_b["conn_id"]
                    ]
                )
                >= 3
            )
        )
        renews = [
            c["t"] for c in fake.calls_named("lease_renew") if c["conn_id"] == assume_b["conn_id"]
        ]
        gaps = [b - a for a, b in zip(renews, renews[1:], strict=False)]
        assert all(0.1 < g < 0.6 for g in gaps)  # ~ every lease_every_s (3 s in production)
        # renewals follow the role: none are sent on the released connection afterwards
        late = [c for c in fake.calls_named("lease_renew") if c["t"] > release["t"]]
        assert all(c["conn_id"] == assume_b["conn_id"] for c in late)
    finally:
        await agent.stop()
        await fake.stop()


async def test_mission_refused_when_another_agent_holds_hands(fixtures_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    scripts = [[], [message_frame(1, "@hands mission a none", room_id="room-2")]]
    fake = await FakeSwitch(scripts, rooms=ROOMS[:2]).start()
    setup_fake(fake, monkeypatch, "desk-laptop", "desk-backup")
    fake.roles["hands"] = {"agent_id": "id-desk-backup", "name": "desk-backup", "renewed": 1e12}
    agent = make(DeskAgent, fixtures_dir, "desk-laptop")
    try:
        await agent.start()
        await wait_for(lambda: "⛔ refused · hands is held by desk-backup" in bodies(fake))
        assert agent.role_room is None
    finally:
        await agent.stop()
        await fake.stop()


async def start_pair(fixtures_dir, monkeypatch, tmp_path, mode="lease", lease_ttl=None):
    monkeypatch.chdir(tmp_path)
    fake = await FakeSwitch([], rooms=ROOMS[:2], lease_ttl=lease_ttl).start()
    setup_fake(fake, monkeypatch, "desk-laptop", "desk-backup")
    laptop = make(DeskAgent, fixtures_dir, "desk-laptop", mode)
    laptop.lease_every_s = 0.1
    backup = make(BackupAgent, fixtures_dir, "desk-backup", mode)
    backup.poll_every_s = 0.1
    await laptop.start()
    await wait_for(lambda: laptop.watcher.room("room-2") is not None)
    ok, _ = await laptop.assume_hands(laptop.watcher.room("room-2"))
    assert ok
    return fake, laptop, backup


async def test_lease_lapse_hands_over_to_backup_and_announces(fixtures_dir, monkeypatch, tmp_path):
    fake, laptop, backup = await start_pair(
        fixtures_dir, monkeypatch, tmp_path, "lease", lease_ttl=0.6
    )
    events = []

    async def collect():
        async for ev in backup.bus.subscribe():
            events.append(ev)

    collector = asyncio.create_task(collect())
    await asyncio.sleep(0)
    try:
        await backup.start()
        await asyncio.sleep(1.0)  # laptop keeps renewing: backup must not take it
        assert fake.roles["hands"]["name"] == "desk-laptop"
        assert not any("🫱" in b for b in bodies(fake))

        await laptop.stop()  # runtime killed: no more renewals, role not released
        await wait_for(lambda: fake.roles.get("hands", {}).get("name") == "desk-backup", 6)
        text = "🫱 hands is now on desk-backup"
        await wait_for(lambda: bodies(fake).count(text) >= 2)  # mission room + HQ
        assert backup.role_room.id == "room-2"
        await wait_for(lambda: any(e.type == "transfer" for e in events))
        transfer = next(e for e in events if e.type == "transfer")
        assert transfer.to_agent == "desk-backup"
        # backup keeps its own lease alive
        n = len(fake.calls_named("lease_renew"))
        await wait_for(lambda: len(fake.calls_named("lease_renew")) > n)
    finally:
        collector.cancel()
        await backup.stop()
        await fake.stop()


async def test_explicit_mode_only_moves_on_release(fixtures_dir, monkeypatch, tmp_path):
    fake, laptop, backup = await start_pair(fixtures_dir, monkeypatch, tmp_path, "explicit")
    try:
        await backup.start()
        await asyncio.sleep(1.0)  # backup polling, laptop holds: nothing moves
        assert fake.roles["hands"]["name"] == "desk-laptop"
        assert not any("🫱" in b for b in bodies(fake))
        assert await laptop.release_hands()  # the owner's `@hands release`
        await wait_for(lambda: fake.roles.get("hands", {}).get("name") == "desk-backup", 6)
        await wait_for(lambda: "🫱 hands is now on desk-backup" in bodies(fake))
    finally:
        await laptop.stop()
        await backup.stop()
        await fake.stop()


async def test_handoff_reaches_hud_ws_stream(fixtures_dir, monkeypatch, tmp_path):
    """The backup's `transfer` and `system` events reach a client of the HUD /ws stream."""
    import json
    import socket

    import websockets

    from roomservice.bus import bus
    from roomservice.hud.server import run_hud

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    fake, laptop, backup = await start_pair(
        fixtures_dir, monkeypatch, tmp_path, "lease", lease_ttl=0.6
    )
    backup.bus = bus  # the module-level bus the HUD serves, as in `roomservice backup`
    hud = asyncio.create_task(run_hud(port))
    seen: list[dict] = []
    try:
        ws = None
        for _ in range(100):
            try:
                ws = await websockets.connect(f"ws://127.0.0.1:{port}/ws")
                break
            except OSError:
                await asyncio.sleep(0.05)
        assert ws is not None
        assert json.loads(await ws.recv())["type"] == "hello"
        await backup.start()
        await laptop.stop()
        end = time.monotonic() + 10

        def done():
            kinds = {m["type"] for m in seen}
            return "transfer" in kinds and any(
                m["type"] == "system" and "desk-backup" in m["text"] for m in seen
            )

        while time.monotonic() < end and not done():
            seen.append(json.loads(await asyncio.wait_for(ws.recv(), 10)))
        transfer = next(m for m in seen if m["type"] == "transfer")
        assert transfer["to_agent"] == "desk-backup"
        assert any(m["type"] == "system" and "desk-backup" in m["text"] for m in seen)
        await ws.close()
    finally:
        hud.cancel()
        await backup.stop()
        await fake.stop()
