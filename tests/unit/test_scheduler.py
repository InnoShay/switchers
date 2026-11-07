"""Scheduler registration, timezone and job behaviour (SPEC §14.4)."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from roomservice.contracts.config import Schedule
from roomservice.scheduler import morning_brief, start_scheduler, wrap_nudge


class Desk:
    def __init__(self, active=None, schedule=None):
        self.cfg = SimpleNamespace(timezone="Asia/Kolkata", schedule=schedule or Schedule())
        self.state = SimpleNamespace(active=active)
        self.posts: list[tuple[str, str]] = []
        self.spoken: list[str] = []
        self.actions = SimpleNamespace(speak=self.spoken.append)

    def hq_rooms(self):
        return [SimpleNamespace(name="hq-a"), SimpleNamespace(name="hq-b")]

    async def _safe_reply(self, room, text, thread_id=None):
        self.posts.append((room.name, text))


class Life:
    def __init__(self):
        self.briefs = 0

    async def brief(self):
        self.briefs += 1


async def test_jobs_registered_with_schedule_and_timezone():
    desk = Desk(schedule=Schedule(morning_brief="07:30", wrap_nudge="22:15"))
    sched = start_scheduler(desk, Life())
    try:
        assert {j.id for j in sched.get_jobs()} == {"morning-brief", "wrap-nudge"}
        assert str(sched.timezone) == "Asia/Kolkata"
        mb = sched.get_job("morning-brief").trigger
        fields = {f.name: str(f) for f in mb.fields}
        assert (fields["hour"], fields["minute"], fields["day_of_week"]) == ("7", "30", "mon-sat")
        wn = {f.name: str(f) for f in sched.get_job("wrap-nudge").trigger.fields}
        assert (wn["hour"], wn["minute"], wn["day_of_week"]) == ("22", "15", "*")
        # mon-sat: after Saturday 07:30 IST the next run is Monday 07:30 IST
        tz = ZoneInfo("Asia/Kolkata")
        nxt = mb.get_next_fire_time(None, datetime(2026, 11, 7, 8, 0, tzinfo=tz))
        assert nxt == datetime(2026, 11, 9, 7, 30, tzinfo=tz)
    finally:
        sched.shutdown(wait=False)


async def test_morning_brief_calls_life():
    life = Life()
    await morning_brief(life)
    assert life.briefs == 1
    await morning_brief(None)  # life not running: no crash


async def test_wrap_nudge_only_with_active_mission():
    idle = Desk(active=None)
    await wrap_nudge(idle)
    assert idle.posts == [] and idle.spoken == []

    busy = Desk(active=object())
    await wrap_nudge(busy)
    assert [r for r, _ in busy.posts] == ["hq-a", "hq-b"]
    text = busy.posts[0][1]
    assert text.startswith("🌙 It's ") and text.endswith('Say "wrap up" when you\'re done.')
    assert busy.spoken == [text.removeprefix("🌙 ")]
