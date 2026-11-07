"""Relay (SPEC §13, §20.2): mirror rules, rate-limit collapse, approval relay, page shot."""

import pytest
from freezegun import freeze_time

from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.config import Settings
from roomservice.contracts.switch import DomainEvent, MessagePayload
from roomservice.desk import pageshot
from roomservice.desk.approvals import Approvals
from roomservice.relay import Relay
from tests.unit.test_desk_queue import HQ, OWNER, desk, posts  # noqa: F401

MISSION = RoomInfo(id="m1", name="mission-volt", kind=RoomKind.MISSION, conn_id="cm")
HQ2 = RoomInfo(id="r2", name="RoomService HQ", kind=RoomKind.HQ, conn_id="c2")
_n = 0


def msg(body, name="concierge", sender="@bot:srv", thread_id=None):
    global _n
    _n += 1
    return MessagePayload(
        addressed=False,
        sender=sender,
        sender_name=name,
        message_id=f"x{_n}",
        body=body,
        timestamp=1,
        thread_id=thread_id,
    )


class Rig:
    def __init__(self, relay_approvals=True):
        self.out: list[tuple] = []
        self.replies: list[tuple] = []
        self.approvals = Approvals(ttl_s=300, publish=lambda e: None)

        async def post(rid, text):
            self.out.append(("post", rid, text))

        async def upload(rid, png, fn, cap):
            self.out.append(("upload", rid, png, fn, cap))

        async def reply(room, text, thread):
            self.replies.append((room.id, text, thread))

        self.relay = Relay(
            settings=Settings(roomservice_relay_approvals=relay_approvals),
            approvals=self.approvals,
            hq_rooms=lambda: [HQ, HQ2],
            post=post,
            upload=upload,
            reply=reply,
        )

    def texts(self):
        return [o[2] for o in self.out if o[0] == "post"]


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setenv("SWITCH_URL", "http://localhost:1")
    return Rig()


KICKOFF = "@desk-laptop mission volt volt\n@builder build the page"


async def test_plan_is_first_concierge_message_after_kickoff(rig):
    await rig.relay.observe(MISSION, msg(KICKOFF))
    assert rig.out == []
    plan = "\n".join(f"step {i}" for i in range(1, 10)) + "\n@builder go."
    await rig.relay.observe(MISSION, msg(plan))
    await rig.relay.observe(MISSION, msg("second concierge message"))
    assert [(o[1]) for o in rig.out] == ["r1", "r2"]  # every HQ room, once
    text = rig.texts()[0]
    assert text.splitlines()[0] == "🧭 plan · mission-volt"
    assert text.splitlines()[1] == "step 1"
    assert len(text.splitlines()) <= 6


async def test_screenshot_upload_mirrored_with_same_png_and_caption(rig):
    await rig.relay.on_desk_upload(MISSION, b"PNG", "shot.png", "📸 volt · x · 10:00 IST")
    assert rig.out == [
        ("upload", "r1", b"PNG", "shot.png", "📸 volt · x · 10:00 IST"),
        ("upload", "r2", b"PNG", "shot.png", "📸 volt · x · 10:00 IST"),
    ]


async def test_desk_approval_text_mirrored(rig):
    text = '⚠️ approval needed · commit "v1" in volt\nOwner: reply  ok K7Q3  or  no K7Q3  (5 min)'
    await rig.relay.on_desk_post(MISSION, text)
    assert rig.texts()[0] == text


async def test_builder_done_whole_word_only(rig):
    await rig.relay.observe(MISSION, msg("undone things\nstill working", name="builder"))
    await rig.relay.observe(MISSION, msg("Page is DONE.\nmore text", name="builder"))
    await rig.relay.observe(MISSION, msg("finished", name="scout"))
    assert rig.texts() == ["🛠️ builder · Page is DONE.", "🛠️ builder · Page is DONE."]


async def test_wrap_mirrored(rig):
    await rig.relay.on_desk_post(MISSION, '✅ wrap · volt · 42 min\n```json\n{"a": 1}\n```')
    assert set(rig.texts()) == {"🌙 wrapped · mission-volt · 42 min"}


async def test_only_mission_rooms_mirror(rig):
    await rig.relay.on_desk_post(HQ, "✅ wrap · volt · 42 min")
    await rig.relay.observe(HQ, msg("all done", name="builder"))
    assert rig.out == []


async def test_rate_limit_collapses_overflow_once_per_minute(rig):
    with freeze_time("2026-11-07 10:00:00") as clock:
        for i in range(9):
            await rig.relay.observe(MISSION, msg(f"item {i} done", name="builder"))
        assert len([t for t in rig.texts() if t.startswith("🛠️")]) == 6 * 2
        clock.tick(30)
        await rig.relay.tick()
        assert not any(t.startswith("…") for t in rig.texts())
        clock.tick(31)
        await rig.relay.tick()
        await rig.relay.tick()
        collapse = [t for t in rig.texts() if t.startswith("…")]
        assert collapse == ["… +3 updates in mission-volt"] * 2  # one per HQ room, once
        # the window has reopened
        await rig.relay.observe(MISSION, msg("again done", name="builder"))
        assert rig.texts()[-1].startswith("🛠️")


async def test_rate_limit_is_per_mission(rig):
    other = RoomInfo(id="m2", name="mission-other", kind=RoomKind.MISSION)
    with freeze_time("2026-11-07 10:00:00"):
        for i in range(8):
            await rig.relay.observe(MISSION, msg(f"{i} done", name="builder"))
        await rig.relay.observe(other, msg("x done", name="builder"))
    assert rig.texts()[-1] == "🛠️ builder · x done"


async def test_every_hq_message_at_most_six_lines(rig):
    await rig.relay.observe(MISSION, msg("\n".join(f"l{i}" for i in range(30))))
    await rig.relay.on_desk_post(
        MISSION, "⚠️ approval needed · x\n" + "\n".join("y" * 5 for _ in range(20))
    )
    assert rig.texts() and all(len(t.splitlines()) <= 6 for t in rig.texts())


# -- builder approval relay (§13.3) ---------------------------------------------------------

ASK = "Run `npm install`?\nAllow once\nAllow for this session"


async def test_builder_ask_creates_approval_and_mirrors(rig):
    await rig.relay.observe(MISSION, msg(ASK, name="builder", thread_id="t9"))
    ap = rig.approvals.open_approvals()[0]
    assert ap.room_id == "m1" and ap.payload.thread_id == "t9"
    first = rig.texts()[0]
    assert (
        first == f"⚠️ builder asks · Run npm install?\nOwner: reply  ok {ap.code}  or  no {ap.code}"
    )


async def test_builder_ask_binds_message_id_without_thread(rig):
    m = msg(ASK, name="builder")
    await rig.relay.observe(MISSION, m)
    assert rig.approvals.open_approvals()[0].payload.thread_id == m.message_id


async def test_relay_approvals_off_creates_nothing(monkeypatch):
    monkeypatch.setenv("SWITCH_URL", "http://localhost:1")
    r = Rig(relay_approvals=False)
    await r.relay.observe(MISSION, msg(ASK, name="builder"))
    assert r.approvals.open_approvals() == []
    assert r.texts()[0] == "⚠️ builder asks · Run npm install? — approve on the laptop"


async def test_desk_posts_yes_or_no_in_the_thread(desk):  # noqa: F811
    room_posts: list[tuple] = []
    orig = desk.http.op

    async def op(name, args, conn_id=None):
        room_posts.append((name, args, conn_id))
        return await orig(name, args, conn_id)

    desk.http.op = op
    desk._rooms_seen[MISSION.id] = MISSION
    for body, answer in (("ok", "yes"), ("no", "no")):
        await desk.relay.observe(MISSION, msg(ASK, name="builder", thread_id="t1"))
        ap = desk.approvals.open_approvals()[-1]
        await desk.on_message(
            HQ,
            DomainEvent(type="message", room_id=HQ.id, payload={}, sequence=1),
            MessagePayload(
                addressed=False,
                sender=OWNER,
                sender_name="owner",
                message_id=f"o-{body}",
                body=f"{body} {ap.code}",
                timestamp=1,
            ),
        )
        assert ("post_message", {"body": answer, "thread_id": "t1"}, "cm") in room_posts
        assert desk.approvals.get(ap.code) is None


async def test_unaddressed_mission_chatter_reaches_the_desk(desk):  # noqa: F811
    assert desk.wants_unaddressed(MISSION, msg("hello"))
    assert not desk.wants_unaddressed(HQ, msg("hello"))


async def test_desk_own_screenshot_in_mission_room_is_mirrored(desk, monkeypatch):  # noqa: F811
    desk.watcher = type("W", (), {"hq_rooms": lambda s: [HQ], "room": lambda s, i: None})()
    uploads = []

    async def up(room_id, files, caption=None, thread_id=None):
        uploads.append((room_id, files[0][1], caption))

    desk.http.upload = up
    await desk.upload(MISSION, b"PNG", "s.png", "📸 screen · screen · 10:00 IST")
    assert uploads == [
        ("m1", b"PNG", "📸 screen · screen · 10:00 IST"),
        ("r1", b"PNG", "📸 screen · screen · 10:00 IST"),
    ]


# -- page screenshot ------------------------------------------------------------------------


class _Fake:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def __call__(self):
        return self

    async def __aenter__(self):
        if self.fail:
            raise RuntimeError("no chromium")
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def chromium(self):
        return self

    async def launch(self, headless):
        self.calls.append(("launch", headless))
        return self

    async def new_context(self, **kw):
        self.calls.append(("context", kw))
        return self

    async def new_page(self):
        return self

    async def goto(self, url, wait_until, timeout):
        self.calls.append(("goto", url, wait_until, timeout))

    async def screenshot(self, **kw):
        return b"\x89PNG"

    async def close(self):
        self.calls.append(("close",))


async def test_capture_page_uses_spec_settings(monkeypatch):
    fake = _Fake()
    monkeypatch.setattr("playwright.async_api.async_playwright", fake)
    assert await pageshot.capture_page("http://localhost:3000") == b"\x89PNG"
    assert ("launch", True) in fake.calls
    assert (
        "context",
        {"viewport": {"width": 1440, "height": 900}, "device_scale_factor": 2},
    ) in fake.calls
    assert ("goto", "http://localhost:3000", "networkidle", 15000) in fake.calls


async def test_capture_page_failure_returns_none(monkeypatch):
    monkeypatch.setattr("playwright.async_api.async_playwright", _Fake(fail=True))
    assert await pageshot.capture_page("http://localhost:3000") is None


async def test_shot_page_falls_back_to_screen_with_suffix(desk, monkeypatch):  # noqa: F811
    monkeypatch.setattr("playwright.async_api.async_playwright", _Fake(fail=True))
    desk.actions.page_shot = pageshot.capture_page
    uploads = []

    async def up(room_id, files, caption=None, thread_id=None):
        uploads.append(caption)

    desk.http.upload = up
    from tests.unit.test_desk_queue import say

    await say(desk, "@hands boot volt")
    await desk.drain()
    await say(desk, "@hands shot page")
    await desk.drain()
    assert uploads and uploads[-1].endswith("(screen fallback)")


# -- RS-10: loop guards -------------------------------------------------------------------


async def test_mentions_are_neutralised_in_mirrors(rig):
    await rig.relay.observe(MISSION, msg("plan\n@hands shot page\n@desk-backup hi"))
    out = rig.texts()
    assert out and all("@hands" not in t and "@desk-" not in t for t in out)
    assert "＠hands shot page" in out[0]


async def test_hq_originated_messages_are_never_mirrored(rig):
    await rig.relay.observe(HQ, msg("plan\nanything"))
    assert rig.out == []


async def test_auto_replies_and_desk_senders_are_ignored(rig):
    offline = "@desk-backup I'm currently offline — my connector isn't reporting in."
    await rig.relay.observe(MISSION, msg(offline, name="concierge"))
    await rig.relay.observe(MISSION, msg("builder done", name="desk-laptop"))
    marked = msg("some plan", name="concierge")
    await rig.relay.observe(MISSION, marked, raw={"com.switch.auto_reply": True})
    assert rig.out == []


async def test_safety_valve_stops_mirroring_and_warns(rig):
    events = []

    class FakeBus:
        def publish(self, ev):
            events.append(ev)

    rig.relay._bus = FakeBus()
    with freeze_time("2026-01-01 00:00:00") as t:
        for i in range(40):
            room = RoomInfo(id=f"m{i}", name=f"mission-{i}", kind=RoomKind.MISSION)
            await rig.relay._mirror(room, "x")
            t.tick(1)
    assert len(rig.texts()) == 2 * 31  # 31 mirrors x 2 HQ rooms, then the valve closes
    assert len(events) == 1 and events[0].level == "warn"
