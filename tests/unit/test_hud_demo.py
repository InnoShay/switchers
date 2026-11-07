import typing

from roomservice.bus import bus
from roomservice.contracts.events import HudEvent
from roomservice.hud import demo


async def test_script_covers_every_event_type(monkeypatch):
    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(demo.asyncio, "sleep", no_sleep)

    expected = {
        t.model_fields["type"].default for t in typing.get_args(typing.get_args(HudEvent)[0])
    }
    assert len(expected) == 14

    seen: set[str] = set()
    orig = bus.publish

    def spy(ev):
        seen.add(ev.type)
        orig(ev)

    monkeypatch.setattr(bus, "publish", spy)
    await demo._script()
    assert seen == expected
