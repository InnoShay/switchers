"""Ignition (SPEC §12.9, §20.2)."""

from datetime import datetime

import pytest

from roomservice.bus import Bus
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Settings, load_desk_config
from roomservice.contracts.events import IgnitionEvent
from roomservice.contracts.switch import MessagePayload
from roomservice.desk.ignition import Ignition, greeting, normalize
from roomservice.desk.receipts import IST

OWNER = "@owner:srv"
HQ = RoomInfo(id="r1", name="roomservice-hq", kind=RoomKind.HQ, conn_id="c1")
MISSION = RoomInfo(id="r2", name="mission-volt", kind=RoomKind.MISSION, conn_id="c2")


def msg(body, sender=OWNER, mid="m1"):
    return MessagePayload(
        addressed=False,
        sender=sender,
        sender_name="owner",
        message_id=mid,
        body=body,
        timestamp=1,
    )


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def rig(fixtures_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SWITCH_URL", "http://localhost:1")
    cfg = load_desk_config(fixtures_dir / "desk_example.yaml")
    log = {"posts": [], "spoken": [], "queued": []}
    bus = Bus()
    events = []
    orig = bus.publish
    bus.publish = lambda ev: (events.append(ev), orig(ev))[1]
    clock = Clock()

    async def post(room, text, thread_id=None):
        log["posts"].append((room.name, text))

    ign = Ignition(
        cfg,
        Settings(),
        owner_ids=lambda: {OWNER},
        post=post,
        speak=log["spoken"].append,
        enqueue=lambda cmd, room: log["queued"].append((cmd.raw, room.name)),
        bus=bus,
        clock=clock,
        now=lambda: datetime(2026, 11, 7, 9, 0, tzinfo=IST),
    )
    return ign, log, events, clock


@pytest.mark.parametrize(
    "body",
    [
        "room service",
        "Room Service!",
        "hey, ROOMSERVICE, morning",
        "room servis please",
        "rumservice",
        "ok room sarvis... volt",
    ],
)
def test_wake_phrase_variants_match(rig, body):
    ign, *_ = rig
    assert ign.matches(HQ, msg(body))


@pytest.mark.parametrize("body", ["room", "the service is down", "roomy services", ""])
def test_non_phrases_do_not_match(rig, body):
    ign, *_ = rig
    assert not ign.matches(HQ, msg(body))


def test_owner_only_and_hq_only(rig):
    ign, *_ = rig
    assert not ign.matches(HQ, msg("room service", sender="@stranger:srv"))
    assert not ign.matches(MISSION, msg("room service"))


def test_keyword_match_and_default_profile(rig):
    ign, *_ = rig
    assert ign.pick_target("room service, let's ship the waitlist") == "volt"
    assert ign.pick_target("Room service, VOLT time") == "volt"
    assert ign.pick_target("room service") == "focus-session"
    assert ign.pick_target("room service, revolt") == "focus-session"  # word match only


async def test_fire_order_and_effects(rig):
    ign, log, events, _ = rig
    target = await ign.fire(HQ, msg("Room service, let's work on volt"))
    assert target == "volt"
    assert isinstance(events[0], IgnitionEvent)  # HUD first
    assert (events[0].project, events[0].lights) == ("volt", "flash")
    assert log["spoken"] == ["Morning. Booting Volt."]
    assert log["posts"] == [("roomservice-hq", "⚡ waking up · opening volt")]
    assert log["queued"] == [("boot volt", "roomservice-hq")]


async def test_default_profile_ignition(rig):
    ign, log, *_ = rig
    assert await ign.fire(HQ, msg("room service")) == "focus-session"
    assert log["posts"][0][1] == "⚡ waking up · opening focus-session"
    assert log["spoken"] == ["Morning. Booting Focus Session."]


async def test_cooldown_60s(rig):
    ign, log, _, clock = rig
    assert await ign.fire(HQ, msg("room service", mid="a")) is not None
    clock.t += 59
    assert await ign.fire(HQ, msg("room service", mid="b")) is None
    clock.t += 2
    assert await ign.fire(HQ, msg("room service", mid="c")) is not None
    assert len(log["queued"]) == 2


async def test_dedupe_by_message_id(rig):
    ign, log, _, clock = rig
    assert await ign.fire(HQ, msg("room service", mid="same")) is not None
    clock.t += 120
    assert await ign.fire(HQ, msg("room service", mid="same")) is None
    assert len(log["queued"]) == 1


@pytest.mark.parametrize(
    "hour,word",
    [(4, "Evening"), (5, "Morning"), (11, "Morning"), (12, "Afternoon"), (16, "Afternoon"),
     (17, "Evening"), (23, "Evening")],
)  # fmt: skip
def test_greeting_by_ist_hour(hour, word):
    assert greeting(datetime(2026, 11, 7, hour, 0, tzinfo=IST)) == word


def test_normalize_strips_punctuation():
    assert normalize("Room, Service!!") == " room service "
