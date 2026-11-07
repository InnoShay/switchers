"""Roles, lease renewal and wrap/resume hardening (SPEC §12.8, §15). No network, dry OS."""

import asyncio
import json

from roomservice import store
from roomservice.agents.desk import LEASE_MAX_FAILS, LEASE_RENEW_S, hands_holder
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.contracts.switch import DomainEvent, MessagePayload, OpError
from tests.unit.test_desk_queue import desk, posts, say  # noqa: F401

M1 = RoomInfo(id="m1", name="mission-one", kind=RoomKind.MISSION, conn_id="c-m1")
M2 = RoomInfo(id="m2", name="mission-two", kind=RoomKind.MISSION, conn_id="c-m2")
_n = 0


def wire(desk, renew=True):  # noqa: F811
    """Give the stub HTTP a renew_lease; `renew` is a bool or a callable returning one."""
    http = desk.test_http
    http.renewed = []

    async def renew_lease(conn_id):
        http.renewed.append(conn_id)
        return renew() if callable(renew) else renew

    http.renew_lease = renew_lease
    return http


async def in_room(desk, room, text):  # noqa: F811
    global _n
    _n += 1
    msg = MessagePayload(
        addressed=True,
        sender="@owner:srv",
        sender_name="owner",
        message_id=f"rr{_n}",
        body=text,
        timestamp=1,
    )
    await desk.on_message(
        room, DomainEvent(type="message", room_id=room.id, payload={}, sequence=_n), msg
    )
    await desk.drain()


def test_lease_constants_match_spec():
    assert LEASE_RENEW_S == 3.0 and LEASE_MAX_FAILS == 3


def test_hands_holder_parses_tolerantly():
    assert hands_holder([]) is None
    assert hands_holder([{"name": "hands", "holder": "desk-laptop"}]) == "desk-laptop"
    assert hands_holder({"roles": [{"name": "hands", "held_by": "desk-backup"}]}) == "desk-backup"
    assert hands_holder([{"name": "hands", "holder": {"name": "x"}}]) == "x"
    assert hands_holder([{"name": "hands", "holder": None}]) is None
    assert hands_holder([{"name": "builder", "holder": "b"}]) is None
    assert hands_holder({"hands": {"holder": "h"}}) == "h"
    assert hands_holder("junk") is None


async def test_mission_releases_old_role_then_assumes_new(desk):  # noqa: F811
    await in_room(desk, M1, "@hands mission one-a none")
    await in_room(desk, M2, "@hands mission two-b none")
    names = [n for n, _ in desk.test_http.ops if n in ("assume_role", "release_role")]
    assert names == ["assume_role", "release_role", "assume_role"]
    assert desk.role_room.id == "m2"
    joined = " ".join(posts(desk))
    assert "✅ mission two-b" in joined and "auto-wrapped one-a" in joined
    saved = json.loads((store.state_dir() / "one-a.json").read_text())
    assert saved["slug"] == "one-a"
    assert not any(p.startswith("✅ wrap") for p in posts(desk))  # silent auto-wrap


async def test_mission_refused_when_hands_held_elsewhere(desk):  # noqa: F811
    http = desk.test_http
    orig = http.op

    async def op(name, args, conn_id=None):
        if name == "assume_role":
            raise OpError(409, "role hands is held")
        if name == "list_roles":
            return [{"name": "hands", "holder": "desk-backup"}]
        return await orig(name, args, conn_id)

    http.op = op
    await in_room(desk, M1, "@hands mission one-a none")
    assert posts(desk)[-1] == "⛔ refused · hands is held by desk-backup"
    assert desk.role_room is None and desk.state.active is None


async def test_lease_renews_while_holding_and_stops_after_release(desk):  # noqa: F811
    http = wire(desk)
    desk.lease_every_s = 0.02
    task = asyncio.create_task(desk._lease_loop())
    try:
        await asyncio.sleep(0.1)
        assert http.renewed == []  # not holding: nothing to renew
        await in_room(desk, M1, "@hands mission one-a none")
        await asyncio.sleep(0.15)
        n = len(http.renewed)
        assert n >= 3 and set(http.renewed) == {"c-m1"}
        await in_room(desk, M1, "@hands release")
        assert desk.role_room is None
        await asyncio.sleep(0.1)
        assert len(http.renewed) <= n + 1
    finally:
        task.cancel()


async def test_three_consecutive_failures_lose_the_role_with_hud_warn(desk):  # noqa: F811
    results = iter([False, False, True] + [False] * 40)
    wire(desk, renew=lambda: next(results))
    events = []

    async def collect():
        async for ev in desk.bus.subscribe():
            events.append(ev)

    c = asyncio.create_task(collect())
    await asyncio.sleep(0)
    await in_room(desk, M1, "@hands mission one-a none")
    desk.lease_every_s = 0.02
    task = asyncio.create_task(desk._lease_loop())
    try:
        await asyncio.sleep(0.07)
        assert desk.role_room is not None  # 2 failures then a success reset the count
        await asyncio.sleep(0.3)
        assert desk.role_room is None
        warns = [e for e in events if e.type == "system" and e.level == "warn"]
        assert warns and "hands role lost" in warns[0].text
    finally:
        task.cancel()
        c.cancel()


async def test_start_lease_renewal_task_is_cancellable(desk):  # noqa: F811
    wire(desk)
    desk.start_lease_renewal()
    t = desk._tasks[-1]
    assert not t.done()
    t.cancel()
    await asyncio.gather(t, return_exceptions=True)
    assert t.cancelled()


# -- wrap / resume (SPEC §12.8) ----------------------------------------------------------------


async def test_wrap_reply_is_exact_fenced_json(desk):  # noqa: F811
    await say(desk, "@hands mission volt-waitlist volt")
    await desk.drain()
    await say(desk, "@hands wrap")
    await desk.drain()
    head, fence, body, close = posts(desk)[-1].split("\n")
    assert head.startswith("✅ wrap · volt-waitlist · ") and head.endswith(" min")
    assert (fence, close) == ("```json", "```")
    data = json.loads(body)
    assert list(data) == [
        "slug",
        "project",
        "wrapped_at",
        "mission_minutes",
        "path",
        "git",
        "opened",
        "screenshot_url",
    ]
    assert data["path"].startswith("~/") and data["screenshot_url"] == "http://localhost:5173"
    assert set(data["opened"]) == {"apps", "urls", "terminals"}
    assert "http://localhost:5173" in data["opened"]["urls"]


async def test_resume_skips_boot_when_booted_and_adds_extra_urls(desk):  # noqa: F811
    desk.state.start_mission("old", "volt", "~/x", "http://localhost:5173")
    desk.state.record_opened("urls", "https://example.org/docs")
    desk.state.record_opened("urls", "http://localhost:5173")
    desk.state.wrap()
    await say(desk, "@hands boot volt")
    await desk.drain()
    boots = [c for c in desk.adapter.calls if c[0] == "open_terminal"]
    await say(desk, "@hands resume volt")
    await desk.drain()
    assert [c for c in desk.adapter.calls if c[0] == "open_terminal"] == boots  # no second boot
    assert ("open_url", ("https://example.org/docs",)) in desk.adapter.calls
    last = posts(desk)[-1]
    assert last.startswith("✅ resume volt · already booted, +1 tab")
    assert "no saved state" not in last


async def test_resume_without_state_boots_with_note(desk):  # noqa: F811
    await say(desk, "@hands resume volt")
    await desk.drain()
    last = posts(desk)[-1]
    assert last.startswith("✅ resume volt · editor") and last.endswith("· no saved state")


async def test_wrap_and_close_all_clear_booted(desk):  # noqa: F811
    await say(desk, "@hands mission m1 volt")
    await desk.drain()
    assert desk.state.is_booted("volt")
    await say(desk, "@hands wrap")
    await desk.drain()
    assert not desk.state.is_booted("volt")
    await say(desk, "@hands resume volt")
    await desk.drain()
    assert desk.state.is_booted("volt")
    desk.actions._forget_opened()  # what `close all` does
    assert not desk.state.is_booted("volt")


async def test_new_mission_auto_wraps_without_commit_and_keeps_booted(desk):  # noqa: F811
    await in_room(desk, M1, "@hands mission one-a volt")
    await in_room(desk, M2, "@hands mission two-b none")
    assert (store.state_dir() / "one-a.json").exists()
    assert desk.state.active.slug == "two-b"
    assert not any(c[0] == "run" for c in desk.adapter.calls)  # no git commit/push
