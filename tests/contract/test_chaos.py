"""Chaos checks (SPEC §20.6) that can run in CI against the fake Switch.

* Switch restarted mid-mission  -> the desk reconnects, no command runs twice.
* Wi-Fi off, then back          -> the desk resumes from its cursor (outage scaled from 20 s to
                                   a few seconds; the backoff cap is 10 s so 20 s behaves the same).
* n8n down                      -> only the life agent shows an error line (needs RS-11).

The "real" 20 s Wi-Fi and Switch-restart runs on the demo machine stay manual (see PR body).
"""

from __future__ import annotations

import asyncio
import importlib.util
import time

import pytest

from roomservice import store
from roomservice.agents.desk import DeskAgent, add_owner
from roomservice.bus import Bus
from roomservice.contracts.config import Settings, load_desk_config
from roomservice.desk.os.dry import DryAdapter
from tests.contract.fake_switch import FakeSwitch, message_frame, sleep


async def wait_for(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


def bodies(fake):
    return [c["args"]["body"] for c in fake.calls_named("op:post_message")]


def count(adapter, op, target=None):
    return len([c for c in adapter.calls if c[0] == op and (target is None or c[1][0] == target)])


@pytest.fixture
async def rig(fixtures_dir, monkeypatch, tmp_path):
    """(start_fake, make_desk): fakes share one port so a restart looks like the same Switch."""
    monkeypatch.chdir(tmp_path)
    fakes: list[FakeSwitch] = []
    agents: list[DeskAgent] = []
    state: dict = {"port": 0}

    async def start_fake(scripts) -> FakeSwitch:
        fake = await FakeSwitch(scripts, port=state["port"]).start()
        state["port"] = int(fake.url.rsplit(":", 1)[1])
        fakes.append(fake)
        return fake

    async def make_desk(fake) -> tuple[DeskAgent, DryAdapter]:
        monkeypatch.setenv("SWITCH_URL", fake.url)
        store.save_agent_creds(fake.url, "desk-laptop", "id-desk-laptop", "key-desk-laptop")
        add_owner("@owner:srv", "owner", "roomservice-hq")
        adapter = DryAdapter(delay_s=0.01)
        agent = DeskAgent(
            cfg=load_desk_config(fixtures_dir / "desk_example.yaml"),
            settings=Settings(),
            adapter=adapter,
            bus=Bus(),
        )
        agents.append(agent)
        await agent.start()
        return agent, adapter

    yield start_fake, make_desk
    for a in agents:
        await a.stop()
    for f in fakes:
        await f.stop()


async def _restart_scenario(rig, outage_s: float):
    start_fake, make_desk = rig
    first = await start_fake(
        [[message_frame(1, "@hands open browser"), sleep(0.3), message_frame(2, "@hands status")]]
    )
    agent, adapter = await make_desk(first)
    await wait_for(lambda: any(b.startswith("✅ status") for b in bodies(first)))
    await wait_for(lambda: count(adapter, "open_app") == 1)

    await first.stop()  # Switch down / Wi-Fi off
    await asyncio.sleep(outage_s)

    # Switch comes back (new process, same address). At-least-once delivery re-sends event 2,
    # then a genuinely new event 3 arrives.
    second = await start_fake(
        [[message_frame(2, "@hands status"), message_frame(3, "@hands open notes")]]
    )
    await wait_for(lambda: any(b.startswith("✅ open notes") for b in bodies(second)), timeout=25)
    await asyncio.sleep(0.4)  # a duplicate would have shown up by now

    # reconnected with the saved cursor, not from head
    reopen = second.ws_opens[0]["query"]
    assert reopen["start_from"] == "2" and reopen["expected_generation"] == "7"
    assert reopen["connection_id"] == first.ws_opens[0]["query"]["connection_id"]
    # no duplicate execution
    assert count(adapter, "open_app") == 2  # browser (before) + notes (after), each exactly once
    assert count(adapter, "open_app", agent.actions.app_target("browser")) == 1
    assert len([b for b in bodies(first) + bodies(second) if b.startswith("✅ status")]) == 1
    assert len([b for b in bodies(second) if b.startswith("✅ open notes")]) == 1
    return agent


async def test_switch_restart_reconnects_without_duplicate_execution(rig):
    agent = await _restart_scenario(rig, outage_s=0.5)
    assert agent.watcher and agent.watcher.any_connected()


async def test_wifi_off_then_back_resumes(rig):
    # scaled: 3 s stands in for the 20 s of §20.6 (reconnect backoff is capped at 10 s)
    await _restart_scenario(rig, outage_s=3.0)


async def test_restart_mid_mission_keeps_the_mission(rig):
    start_fake, make_desk = rig
    first = await start_fake([[message_frame(1, "@hands mission volt-waitlist volt")]])
    agent, adapter = await make_desk(first)
    await wait_for(lambda: any(b.startswith("✅ task") for b in bodies(first)))
    boot_opens = count(adapter, "open_url")

    await first.stop()
    await asyncio.sleep(0.3)
    second = await start_fake([[message_frame(1, "@hands mission volt-waitlist volt")]])
    await wait_for(lambda: bool(second.ws_opens), timeout=25)
    await asyncio.sleep(0.5)
    # the replayed mission command is not run again (cursor says seq 1 was handled)
    assert not any(b.startswith("✅ task") for b in bodies(second))
    assert count(adapter, "open_url") == boot_opens
    assert agent.state.active and agent.state.active.slug == "volt-waitlist"


@pytest.mark.skipif(
    importlib.util.find_spec("roomservice.agents.life") is None
    or not hasattr(__import__("roomservice.agents.life", fromlist=["x"]), "LifeAgent"),
    reason="LifeAgent (RS-11, Yash) is not merged yet: n8n-down chaos check needs it",
)
async def test_n8n_down_gives_only_the_life_error_line():  # pragma: no cover - until RS-11
    import httpx
    import respx

    from roomservice.agents.life import LifeAgent  # type: ignore[attr-defined]

    assert LifeAgent is not None
    with respx.mock:
        respx.post(url__regex=r".*webhook/roomservice-life").mock(
            side_effect=httpx.ConnectError("n8n down")
        )
        pytest.skip("wire LifeAgent.handle once RS-11 lands: expect a single one-line n8n error")
