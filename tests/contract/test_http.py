"""SwitchHTTPClient against the fake Switch: retries, ops, upload (SPEC §11.2)."""

import httpx
import pytest
import respx

from roomservice.contracts.switch import OpError
from roomservice.switch.http import SwitchHTTPClient
from tests.contract.fake_switch import FakeSwitch


async def test_roundtrip_against_fake():
    fake = await FakeSwitch().start()
    c = SwitchHTTPClient(fake.url, agent_id="a1", api_key="k", registration_key="r")
    try:
        assert await c.health()
        assert await c.register("x", "X", "d", "roomservice-desk") == ("id-x", "key-x")
        with pytest.raises(OpError) as e:
            await c.register("x", "X", "d", "roomservice-desk")
        assert e.value.status == 409
        await c.op("post_message", {"body": "hi", "thread_id": None}, "conn")
        call = fake.calls_named("op:post_message")[0]
        assert call["args"] == {"body": "hi"} and call["conn_id"] == "conn"
        assert await c.post("room-1", "t") == "evt-1"
        await c.upload("room-1", [("a.png", b"png", "image/png")], "cap")
        assert fake.calls_named("media")[0]["size"] == 3
        assert await c.renew_lease("conn")
    finally:
        await c.aclose()
        await fake.stop()


@respx.mock
async def test_retries_5xx_never_4xx_and_typing_swallows():
    c = SwitchHTTPClient("http://sw", agent_id="a", api_key="k", retry_delays=(0, 0, 0))
    ok = httpx.Response(200, json={"event_id": "e"})
    route = respx.post("http://sw/agents/a/message").mock(
        side_effect=[httpx.Response(503), httpx.Response(500), ok]
    )
    assert await c.post("r", "x") == "e"
    assert route.call_count == 3
    bad = respx.post("http://sw/agents/a/ops/foo").mock(
        return_value=httpx.Response(400, json={"detail": "bad"})
    )
    with pytest.raises(OpError):
        await c.op("foo", {})
    assert bad.call_count == 1
    respx.post("http://sw/agents/a/typing").mock(side_effect=httpx.ConnectError("x"))
    await c.typing("r", True)
    await c.aclose()
