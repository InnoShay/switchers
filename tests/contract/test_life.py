"""Life agent (SPEC §20.3): message -> respx-mocked n8n -> reply; n8n down -> one clear line."""

import asyncio
import json
import time

import httpx
import respx

from roomservice import store
from roomservice.agents.life import START_CMD, LifeAgent
from roomservice.bus import Bus
from roomservice.contracts.config import Settings
from tests.contract.fake_switch import FakeSwitch, message_frame

N8N = "http://localhost:5678/webhook/roomservice-life"


async def wait_for(cond, timeout=8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not met in time")


def bodies(fake):
    return [c["args"]["body"] for c in fake.calls_named("op:post_message")]


async def _setup(monkeypatch, script):
    fake = await FakeSwitch([script]).start()
    monkeypatch.setenv("SWITCH_URL", fake.url)
    monkeypatch.setenv("N8N_LIFE_URL", N8N)
    monkeypatch.setenv("N8N_LIFE_TOKEN", "change-me")  # never read the developer's real .env
    store.save_agent_creds(fake.url, "life", "id-life", "key-life")
    bus = Bus()
    agent = LifeAgent(settings=Settings(), bus=bus, mission_slug=lambda: "volt-waitlist")
    return fake, bus, agent


async def test_ask_posts_n8n_reply(monkeypatch):
    with respx.mock(assert_all_called=False) as m:
        m.route(host="127.0.0.1").pass_through()
        route = m.post(N8N).mock(
            return_value=httpx.Response(200, json={"reply": "No events today."})
        )
        fake, bus, agent = await _setup(monkeypatch, [message_frame(1, "@life what's on today?")])
        try:
            await agent.start()
            await wait_for(lambda: bodies(fake))
            assert bodies(fake) == ["🗓️ No events today."]
            req = route.calls.last.request
            assert req.headers["X-RoomService-Token"] == "change-me"
            sent = json.loads(req.content)
            assert sent["text"] == "what's on today?"
            assert sent["sender_name"] == "owner" and sent["room_name"] == "roomservice-hq"
            assert sent["mission_slug"] == "volt-waitlist"
            assert sent["tz"] == "Asia/Kolkata" and sent["mode"] == "ask"
            assert sent["now_iso"].endswith("+05:30")
            assert bus.snapshot().connections.n8n is True
        finally:
            await agent.stop()
            await fake.stop()


async def test_n8n_down_replies_one_line_and_warns_hud(monkeypatch):
    with respx.mock(assert_all_called=False) as m:
        m.route(host="127.0.0.1").pass_through()
        m.post(N8N).mock(side_effect=httpx.ConnectError("refused"))
        fake, bus, agent = await _setup(monkeypatch, [message_frame(1, "@life ping")])
        events: list = []

        async def collect():
            async for ev in bus.subscribe():
                events.append(ev)

        collector = asyncio.create_task(collect())
        await asyncio.sleep(0)
        try:
            await agent.start()
            await wait_for(lambda: bodies(fake))
            assert bodies(fake) == [f"⛔ life · n8n not reachable at {N8N}. Start it: {START_CMD}"]
            assert bus.snapshot().connections.n8n is False

            def warns():
                return [e for e in events if e.type == "system" and e.level == "warn"]

            await wait_for(lambda: bool(warns()))
            assert "n8n not reachable" in warns()[0].text
            await wait_for(lambda: [e for e in events if e.type == "agent_state"][-1:] != [])
            assert [e.state for e in events if e.type == "agent_state"][-1] == "idle"
        finally:
            collector.cancel()
            await agent.stop()
            await fake.stop()


async def test_non_200_is_treated_as_down(monkeypatch):
    with respx.mock(assert_all_called=False) as m:
        m.route(host="127.0.0.1").pass_through()
        m.post(N8N).mock(return_value=httpx.Response(403, json={"message": "Forbidden"}))
        fake, bus, agent = await _setup(monkeypatch, [message_frame(1, "@life hi")])
        try:
            await agent.start()
            await wait_for(lambda: bodies(fake))
            assert bodies(fake)[0].startswith("⛔ life · n8n not reachable")
            assert bus.snapshot().connections.n8n is False
        finally:
            await agent.stop()
            await fake.stop()


async def test_brief_posts_in_hq_room(monkeypatch):
    with respx.mock(assert_all_called=False) as m:
        m.route(host="127.0.0.1").pass_through()
        route = m.post(N8N).mock(return_value=httpx.Response(200, json={"reply": "2 events."}))
        fake, bus, agent = await _setup(monkeypatch, [])
        try:
            await agent.start()
            await wait_for(lambda: agent.hq_rooms())
            await agent.brief()
            assert bodies(fake) == ["☀️ Morning brief\n2 events."]
            assert json.loads(route.calls.last.request.content)["mode"] == "brief"
        finally:
            await agent.stop()
            await fake.stop()
