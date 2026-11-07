import pytest
from freezegun import freeze_time

from roomservice.bus import Bus
from roomservice.contracts.events import ApprovalClosedEvent, ApprovalOpenEvent
from roomservice.desk.approvals import CODE_ALPHABET, Approvals, parse_resolution

OWNER = "owner-1"


@pytest.fixture
def events():
    return []


@pytest.fixture
def ap(events):
    return Approvals(ttl_s=300, publish=events.append)


def test_alphabet_exact():
    assert CODE_ALPHABET == "ACDEFGHJKMNPQRTUVWXY3479"
    for ambiguous in "0O1IL5S2Z6B8":
        assert ambiguous not in CODE_ALPHABET


@freeze_time("2026-11-07 10:00:00")
def test_code_shape(ap):
    for _ in range(50):
        a = ap.create('commit "x"', "room-1")
        assert len(a.code) == 4 and set(a.code) <= set(CODE_ALPHABET)
        ap.resolve(f"ok {a.code}", OWNER, "Lakshay", {OWNER})


@freeze_time("2026-11-07 10:00:00")
def test_codes_unique_among_open(events):
    seq = iter("AAAAAAAACCCC")  # first two codes collide, so the second is regenerated
    ap = Approvals(publish=events.append, rand=lambda _alpha: next(seq))
    a = ap.create("push", "r")
    b = ap.create("push", "r")
    assert (a.code, b.code) == ("AAAA", "CCCC")


@freeze_time("2026-11-07 10:00:00")
def test_open_event_and_hook(events):
    opened = []
    ap = Approvals(ttl_s=300, publish=events.append, on_open=opened.append)
    a = ap.create('commit "waitlist page v1"', "room-1")
    ev = events[0]
    assert isinstance(ev, ApprovalOpenEvent)
    assert ev.code == a.code and ev.cmd == 'commit "waitlist page v1"'
    assert ev.expires_at == a.expires_at_ms
    assert ev.expires_at - int(a.created_at * 1000) == 300_000
    assert opened == [a]


def test_default_publish_goes_through_bus(monkeypatch):
    import roomservice.desk.approvals as mod

    fresh = Bus()
    monkeypatch.setattr(mod, "default_bus", fresh)
    a = mod.Approvals().create("push", "r")
    assert fresh.snapshot().crew[0].state == "needs_you"
    mod.Approvals(publish=fresh.publish).resolve(f"ok {a.code}", OWNER, "x", {OWNER})


def test_ttl_comes_from_limits(fixtures_dir):
    from roomservice.contracts.config import load_desk_config

    cfg = load_desk_config(fixtures_dir / "desk_example.yaml")
    with freeze_time("2026-11-07 10:00:00"):
        a = Approvals(ttl_s=cfg.limits.approval_ttl_s).create("push", "r")
        assert a.expires_at - a.created_at == 300


def test_ok_closes_and_publishes(ap, events):
    with freeze_time("2026-11-07 10:00:00"):
        a = ap.create("push", "room-1")
    with freeze_time("2026-11-07 10:01:00"):
        r = ap.resolve(f"ok {a.code}", OWNER, "Lakshay", {OWNER})
    assert r is not None and r.result == "ok" and r.by == "Lakshay"
    assert r.approval is a and a.status == "closed"
    assert ap.open_approvals() == []
    closed = events[-1]
    assert isinstance(closed, ApprovalClosedEvent)
    assert (closed.code, closed.result, closed.by) == (a.code, "ok", "Lakshay")


def test_no_closes(ap, events):
    with freeze_time("2026-11-07 10:00:00"):
        a = ap.create("push", "room-1")
        r = ap.resolve(f"no {a.code}", OWNER, "Lakshay", {OWNER})
    assert r.result == "no"
    assert events[-1].result == "no"


def test_ttl_expiry_on_resolve(ap, events):
    with freeze_time("2026-11-07 10:00:00"):
        a = ap.create("push", "room-1")
    with freeze_time("2026-11-07 10:04:59"):
        assert ap.get(a.code) is a
    with freeze_time("2026-11-07 10:05:00"):
        r = ap.resolve(f"ok {a.code}", OWNER, "Lakshay", {OWNER})
    assert r.result == "expired" and a.status == "expired"
    assert events[-1].result == "expired" and events[-1].by is None
    assert ap.open_approvals() == []


def test_just_before_ttl_still_resolves(ap):
    with freeze_time("2026-11-07 10:00:00"):
        a = ap.create("push", "room-1")
    with freeze_time("2026-11-07 10:04:59"):
        assert ap.resolve(f"ok {a.code}", OWNER, "L", {OWNER}).result == "ok"


def test_sweep_expires_due_only(ap, events):
    with freeze_time("2026-11-07 10:00:00"):
        old = ap.create("push", "r")
    with freeze_time("2026-11-07 10:03:00"):
        new = ap.create("commit", "r")
    with freeze_time("2026-11-07 10:06:00"):
        gone = ap.sweep()
    assert gone == [old]
    assert ap.open_approvals() == [new]
    assert [e.result for e in events if isinstance(e, ApprovalClosedEvent)] == ["expired"]


def test_on_close_hook(events):
    closed = []
    ap = Approvals(publish=events.append, on_close=lambda a, res: closed.append((a.code, res)))
    with freeze_time("2026-11-07 10:00:00"):
        a = ap.create("push", "r")
        ap.resolve(f"no {a.code}", OWNER, "L", {OWNER})
    assert closed == [(a.code, "no")]


@freeze_time("2026-11-07 10:00:00")
def test_non_owner_cannot_resolve(ap):
    a = ap.create("push", "r")
    assert ap.resolve(f"ok {a.code}", "stranger", "Eve", {OWNER}) is None
    assert ap.get(a.code) is a and a.status == "open"


@freeze_time("2026-11-07 10:00:00")
def test_agent_cannot_resolve_even_with_owner_id(ap):
    a = ap.create("push", "r")
    assert ap.resolve(f"ok {a.code}", OWNER, "builder", {OWNER}, is_agent=True) is None
    assert a.status == "open"


@freeze_time("2026-11-07 10:00:00")
def test_display_name_spoof_does_not_count(ap):
    a = ap.create("push", "r")
    assert ap.resolve(f"ok {a.code}", "evil", "Lakshay", {OWNER}) is None


@freeze_time("2026-11-07 10:00:00")
def test_resolution_from_any_room(ap):
    a = ap.create("push", "room-1")  # asked in room-1; the reply carries no room at all
    r = ap.resolve(f"ok {a.code}", OWNER, "L", {OWNER})
    assert r.result == "ok" and r.approval.room_id == "room-1"


@freeze_time("2026-11-07 10:00:00")
def test_unknown_code(ap):
    ap.create("push", "r")
    r = ap.resolve("ok ZZZZ", OWNER, "L", {OWNER})
    assert r.result == "unknown" and r.approval is None


@freeze_time("2026-11-07 10:00:00")
def test_non_resolution_text_returns_none(ap):
    assert ap.resolve("hello there", OWNER, "L", {OWNER}) is None


@freeze_time("2026-11-07 10:00:00")
def test_cannot_resolve_twice(ap):
    a = ap.create("push", "r")
    assert ap.resolve(f"ok {a.code}", OWNER, "L", {OWNER}).result == "ok"
    assert ap.resolve(f"ok {a.code}", OWNER, "L", {OWNER}).result == "unknown"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ok K7Q3", ("ok", "K7Q3")),
        ("no K7Q3", ("no", "K7Q3")),
        ("OK K7Q3", ("ok", "K7Q3")),
        ("ok k7q3", ("ok", "K7Q3")),
        ("approve K7Q3", ("ok", "K7Q3")),
        ("yes K7Q3", ("ok", "K7Q3")),
        ("deny K7Q3", ("no", "K7Q3")),
        ("reject K7Q3", ("no", "K7Q3")),
        ("  ok K7Q3  ", ("ok", "K7Q3")),
        ("@hands ok K7Q3", ("ok", "K7Q3")),
        ("@desk-laptop, ok K7Q3", ("ok", "K7Q3")),
        ("@desk-laptop ok K7Q3", ("ok", "K7Q3")),
        ("ok   K7Q3", ("ok", "K7Q3")),
        ("ok K7Q", None),
        ("ok K7Q33", None),
        ("ok", None),
        ("okay K7Q3", None),
        ("ok K7Q3 please", None),
        ("sure ok K7Q3", None),
        ("", None),
    ],
)
def test_regex_variants(text, expected):
    assert parse_resolution(text) == expected
