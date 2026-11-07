"""Scheduler (SPEC §14.4): morning-brief and wrap-nudge, APScheduler in the desk's timezone."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from roomservice.desk import receipts
from roomservice.log import get_logger

log = get_logger("scheduler")


def _hm(value: str) -> tuple[int, int]:
    h, m = value.split(":")
    return int(h), int(m)


async def wrap_nudge(desk: Any) -> None:
    """Only when a mission is active: post in every HQ room and speak it."""
    if desk.state.active is None:
        return
    when = receipts.hhmm_ist(datetime.now(receipts.IST))
    spoken = f"It's {when}. Say \"wrap up\" when you're done."
    for room in desk.hq_rooms():
        await desk._safe_reply(room, f"🌙 {spoken}")
    desk.actions.speak(spoken)


async def morning_brief(life: Any) -> None:
    if life is None:
        log.warning("morning-brief skipped: life agent not running")
        return
    await life.brief()


def start_scheduler(desk, life) -> AsyncIOScheduler:
    """Register both jobs from `desk.cfg` (schedule + timezone) and start. Needs a running loop."""
    cfg = desk.cfg
    tz = cfg.timezone
    sched = AsyncIOScheduler(timezone=tz)
    mh, mm = _hm(cfg.schedule.morning_brief)
    wh, wm = _hm(cfg.schedule.wrap_nudge)
    sched.add_job(
        morning_brief,
        CronTrigger(day_of_week=cfg.schedule.morning_days, hour=mh, minute=mm, timezone=tz),
        args=[life],
        id="morning-brief",
        replace_existing=True,
    )
    sched.add_job(
        wrap_nudge,
        CronTrigger(hour=wh, minute=wm, timezone=tz),
        args=[desk],
        id="wrap-nudge",
        replace_existing=True,
    )
    sched.start()
    return sched
