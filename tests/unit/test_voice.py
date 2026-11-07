import asyncio

from roomservice.contracts.config import Voice
from roomservice.voice import MAX_PENDING, MAX_TEXT, SpeechQueue


class FakeAdapter:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[str, str, int]] = []
        self.fail_on = fail_on

    async def speak(self, text, voice, rate):
        if text == self.fail_on:
            raise RuntimeError("boom")
        await asyncio.sleep(0)
        self.calls.append((text, voice, rate))


async def test_speaks_in_order_with_voice_settings():
    ad = FakeAdapter()
    q = SpeechQueue(ad, Voice(voice_name="Alex", rate=150))
    q.start()
    q.say("one")
    q.say("two")
    await q.drain()
    await q.stop()
    assert ad.calls == [("one", "Alex", 150), ("two", "Alex", 150)]


async def test_disabled_voice_is_silent():
    ad = FakeAdapter()
    q = SpeechQueue(ad, Voice(enabled=False))
    q.start()
    assert q.say("hello") is False
    await q.drain()
    await q.stop()
    assert ad.calls == []


async def test_empty_text_ignored_and_long_text_clipped():
    ad = FakeAdapter()
    q = SpeechQueue(ad)
    q.start()
    assert q.say("   ") is False
    q.say("x" * 500)
    await q.drain()
    await q.stop()
    assert len(ad.calls[0][0]) == MAX_TEXT


async def test_adapter_error_does_not_kill_worker():
    ad = FakeAdapter(fail_on="bad")
    q = SpeechQueue(ad)
    q.start()
    q.say("bad")
    q.say("good")
    await q.drain()
    await q.stop()
    assert [c[0] for c in ad.calls] == ["good"]


async def test_overflow_drops_oldest():
    ad = FakeAdapter()
    q = SpeechQueue(ad)  # worker not started yet, so lines pile up
    for i in range(MAX_PENDING + 3):
        q.say(f"line {i}")
    assert q.pending == MAX_PENDING
    q.start()
    await q.drain()
    await q.stop()
    assert ad.calls[0][0] == "line 3"
    assert ad.calls[-1][0] == f"line {MAX_PENDING + 2}"
