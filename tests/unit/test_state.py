import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from roomservice import store
from roomservice.desk.state import NoActiveMission, StateManager

IST = timezone(timedelta(hours=5, minutes=30))


class Clock:
    def __init__(self, start: datetime):
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw):
        self.t += timedelta(**kw)


@pytest.fixture
def clock():
    return Clock(datetime(2026, 11, 7, 21, 5, 5, tzinfo=IST))


def fake_git(path: Path):
    return {"branch": "main", "head": "3f2a91c", "dirty_files": 2}


@pytest.fixture
def sm(clock):
    return StateManager(git_info=fake_git, now=clock)


def start_volt(sm):
    sm.start_mission(
        "volt-waitlist",
        "volt",
        Path.home() / "roomservice-workspace/projects/volt",
        screenshot_url="http://localhost:5173",
    )
    sm.record_opened("apps", "music")
    sm.record_opened("urls", "http://localhost:5173")
    sm.record_opened("urls", "https://github.com")
    sm.record_opened("urls", "https://github.com")  # dup ignored
    sm.record_opened("terminals", "dev")


def test_wrap_json_shape_matches_spec(sm, clock):
    start_volt(sm)
    clock.advance(minutes=96)
    state = sm.wrap()
    assert state == {
        "slug": "volt-waitlist",
        "project": "volt",
        "wrapped_at": "2026-11-07T22:41:05+05:30",
        "mission_minutes": 96,
        "path": "~/roomservice-workspace/projects/volt",
        "git": {"branch": "main", "head": "3f2a91c", "dirty_files": 2},
        "opened": {
            "apps": ["music"],
            "urls": ["http://localhost:5173", "https://github.com"],
            "terminals": ["dev"],
        },
        "screenshot_url": "http://localhost:5173",
    }
    assert list(state) == [
        "slug",
        "project",
        "wrapped_at",
        "mission_minutes",
        "path",
        "git",
        "opened",
        "screenshot_url",
    ]


def test_wrap_writes_state_file_and_clears_active(sm, clock):
    start_volt(sm)
    assert store.state_dir().joinpath("active.json").exists()
    clock.advance(minutes=10)
    state = sm.wrap()
    saved = json.loads((store.state_dir() / "volt-waitlist.json").read_text())
    assert saved == state
    assert sm.active is None
    assert not (store.state_dir() / "active.json").exists()


def test_wrap_without_mission_raises(sm):
    with pytest.raises(NoActiveMission):
        sm.wrap()


def test_wrap_clears_booted(sm):
    start_volt(sm)
    sm.mark_booted("volt")
    assert sm.is_booted("volt")
    sm.wrap()
    assert not sm.is_booted("volt")


def test_forget_booted(sm):
    sm.mark_booted("volt")
    sm.mark_booted("other")
    sm.forget_booted("volt")
    assert not sm.is_booted("volt") and sm.is_booted("other")
    sm.forget_booted()
    assert not sm.is_booted("other")


def test_active_json_survives_restart(sm, clock):
    start_volt(sm)
    again = StateManager(git_info=fake_git, now=clock)
    assert again.active is not None
    assert again.active.slug == "volt-waitlist"
    assert again.active.urls == ["http://localhost:5173", "https://github.com"]


def test_mission_without_project(sm, clock):
    sm.start_mission("scratch", None)
    clock.advance(minutes=3)
    state = sm.wrap()
    assert state["project"] is None and state["path"] is None and state["git"] is None
    assert state["mission_minutes"] == 3


def test_auto_wrap_on_new_mission(sm, clock):
    start_volt(sm)
    sm.mark_booted("volt")
    clock.advance(minutes=30)
    auto = sm.start_mission("next-thing", "volt", Path.home() / "x")
    assert auto is not None and auto["slug"] == "volt-waitlist"
    assert auto["mission_minutes"] == 30
    assert (store.state_dir() / "volt-waitlist.json").exists()
    assert sm.active is not None and sm.active.slug == "next-thing"
    assert sm.is_booted("volt")  # apps are still open after a silent auto-wrap


def test_first_mission_has_no_autowrap(sm):
    assert sm.start_mission("a", None) is None


def test_bad_slug_rejected(sm):
    for bad in ("../evil", "a/b", "", ".hidden", "x y"):
        with pytest.raises(ValueError):
            sm.start_mission(bad, None)


def test_resume_picks_newest_for_project(sm, clock):
    sm.start_mission("old", "volt", Path.home() / "v")
    clock.advance(minutes=5)
    sm.wrap()
    clock.advance(hours=3)
    sm.start_mission("newer", "volt", Path.home() / "v")
    sm.record_opened("urls", "https://github.com")
    clock.advance(minutes=5)
    sm.wrap()
    clock.advance(hours=1)
    sm.start_mission("other-project", "blog", Path.home() / "b")
    clock.advance(minutes=1)
    sm.wrap()
    latest = sm.latest_state("volt")
    assert latest is not None and latest["slug"] == "newer"
    assert sm.latest_state("blog")["slug"] == "other-project"
    assert sm.latest_state("missing") is None


def test_resume_ignores_active_and_corrupt_files(sm, clock):
    sm.start_mission("live", "volt", Path.home() / "v")  # active.json exists, project volt
    (store.state_dir() / "junk.json").write_text("{not json")
    (store.state_dir() / "list.json").write_text("[1]")
    assert sm.latest_state("volt") is None


def test_resume_extra_urls(sm):
    saved = {"opened": {"urls": ["http://localhost:5173", "https://github.com", "https://a.b"]}}
    assert sm.resume_extra_urls(saved, ["http://localhost:5173"]) == [
        "https://github.com",
        "https://a.b",
    ]
    assert sm.resume_extra_urls({}, []) == []


def test_git_info_is_injected_with_expanded_path(clock):
    seen = []

    def spy(path):
        seen.append(path)
        return {"branch": "dev", "head": None, "dirty_files": 0}

    sm = StateManager(git_info=spy, now=clock)
    sm.start_mission("s", "volt", Path.home() / "proj")
    state = sm.wrap()
    assert seen == [Path.home() / "proj"]
    assert state["path"] == "~/proj"
    assert state["git"]["branch"] == "dev"
