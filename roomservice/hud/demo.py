"""`roomservice hud --demo`: a scripted 90-second loop of every HUD event type (SPEC §16.1)."""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from pathlib import Path

from roomservice import store
from roomservice.bus import bus
from roomservice.contracts.events import (
    CREW_COLORS,
    ActionEndEvent,
    ActionStartEvent,
    AgentStateEvent,
    ApprovalClosedEvent,
    ApprovalOpenEvent,
    Connections,
    CrewMember,
    FreezeEvent,
    HelloEvent,
    IgnitionEvent,
    MessageEvent,
    MissionEvent,
    ScreenshotEvent,
    SpeakEvent,
    SystemEvent,
    TransferEvent,
    now_ms,
)

SAMPLE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sample-shot.png"
SHOT_NAME = "shot-volt-143201.png"
SLUG = "volt-waitlist"
HQ, MISSION = "RoomService HQ", f"mission-{SLUG}"
_CREW = ["you", "concierge", "builder", "scout", "hands", "life"]


def _hello(state: str = "idle", mission: str | None = None) -> HelloEvent:
    return HelloEvent(
        mission=mission,
        crew=[CrewMember(name=k, color=CREW_COLORS[k], state=state) for k in _CREW],  # type: ignore[arg-type]
        connections=Connections(switch=True, n8n=True),
        machine="laptop",
    )


def _msg(room: str, kind: str, name: str, agent: str, body: str, addressed: bool = False):
    return MessageEvent(
        room=room,
        room_kind=kind,
        sender_name=name,
        agent=agent,
        body=body,
        addressed=addressed,  # type: ignore[arg-type]
    )


async def _freeze(on: bool) -> None:
    bus.publish(FreezeEvent(on=on))


async def _script() -> None:
    """One pass through the story. Delays add up to roughly 90 s."""
    p = bus.publish
    started = now_ms()
    p(_hello())
    p(SystemEvent(level="info", text="demo mode: scripted events"))
    await asyncio.sleep(3)

    p(IgnitionEvent(project="volt", lights="flash"))
    p(SpeakEvent(text="Evening. Booting Volt."))
    p(ActionStartEvent(id="a1", verb="boot", args=["volt"], room=HQ))
    await asyncio.sleep(1)
    p(_msg(HQ, "hq", "Yash", "you", "Room service. Tonight we ship the Volt waitlist page.", True))
    await asyncio.sleep(3)
    p(ActionEndEvent(id="a1", ok=True, ms=3400, summary="editor, 1 terminal, 2 tabs, focus, music"))
    p(AgentStateEvent(agent="concierge", state="working"))
    await asyncio.sleep(3)

    p(MissionEvent(slug=SLUG, title="Volt waitlist page", started_at=started))
    p(
        _msg(
            HQ,
            "hq",
            "Concierge",
            "concierge",
            f"Mission card: {SLUG}. Crew assembled in {MISSION}.",
        )
    )
    p(AgentStateEvent(agent="concierge", state="idle"))
    p(
        _msg(
            MISSION,
            "mission",
            "Concierge",
            "concierge",
            "Plan: build the page, show a shot. @builder go.",
            True,
        )
    )
    await asyncio.sleep(3)
    p(
        _msg(
            MISSION,
            "mission",
            "Life",
            "life",
            "Calendar blocked 21:00 to 23:00. Reminder set for 23:00.",
        )
    )
    p(_msg(MISSION, "mission", "Builder", "builder", "On it. Editing src/style.css."))
    p(AgentStateEvent(agent="builder", state="working"))
    await asyncio.sleep(5)

    p(ActionStartEvent(id="a2", verb="run", args=["test"], room=MISSION))
    await asyncio.sleep(2)
    p(ActionEndEvent(id="a2", ok=True, ms=1800, summary="exit 0"))
    p(
        _msg(
            MISSION,
            "mission",
            "Scout",
            "scout",
            "Found 3 reference waitlist pages. Registered in the room.",
        )
    )
    await asyncio.sleep(4)

    p(_msg(MISSION, "mission", "Yash", "you", "show me", True))
    p(ActionStartEvent(id="a3", verb="shot", args=["page"], room=MISSION))
    await asyncio.sleep(2)
    p(ActionEndEvent(id="a3", ok=True, ms=1200, summary="uploaded"))
    p(
        ScreenshotEvent(
            url=f"/shots/{SHOT_NAME}", caption="📸 volt · http://localhost:5173 · 14:32 IST"
        )
    )
    p(_msg(MISSION, "mission", "Builder", "builder", "Make the button orange and bigger? Done."))
    await asyncio.sleep(8)

    p(ActionStartEvent(id="a4", verb="commit", args=["waitlist page v1"], room=MISSION))
    p(
        ApprovalOpenEvent(
            code="K7Q3", cmd='commit "waitlist page v1" in volt', expires_at=now_ms() + 20_000
        )
    )
    p(SpeakEvent(text="Approval needed."))
    await asyncio.sleep(8)
    p(ApprovalClosedEvent(code="K7Q3", result="ok", by="Yash"))
    p(ActionEndEvent(id="a4", ok=True, ms=900, summary="committed 3f2a91c"))
    p(AgentStateEvent(agent="builder", state="idle"))
    await asyncio.sleep(4)

    p(_msg(MISSION, "mission", "Yash", "you", "Goodnight, wrap up.", True))
    p(FreezeEvent(on=True))
    await asyncio.sleep(3)
    p(FreezeEvent(on=False))
    p(TransferEvent(from_agent="desk-laptop", to_agent="desk-backup"))
    p(SystemEvent(level="warn", text="hands is now on desk-backup"))
    await asyncio.sleep(6)

    p(ActionStartEvent(id="a5", verb="wrap", args=[], room=MISSION))
    await asyncio.sleep(2)
    p(ActionEndEvent(id="a5", ok=True, ms=2000, summary="wrap · volt-waitlist · 96 min"))
    p(SpeakEvent(text="Goodnight."))
    p(_msg(HQ, "hq", "Hands", "hands", "✅ wrap · volt-waitlist · 96 min"))
    p(ApprovalOpenEvent(code="X9AF", cmd="close all", expires_at=now_ms() + 6_000))
    await asyncio.sleep(7)
    p(ApprovalClosedEvent(code="X9AF", result="expired", by=None))
    p(SystemEvent(level="error", text="demo: sample error line"))
    await asyncio.sleep(10)
    p(_hello())  # back to idle and no mission, loop restarts


async def run_demo(port: int) -> None:
    """Serve the HUD and loop the scripted story forever."""
    from roomservice.hud.server import run_hud

    if SAMPLE.is_file():
        shutil.copyfile(SAMPLE, store.shots_dir() / SHOT_NAME)
    bus.on_freeze = _freeze
    bus.set_connection("switch", True)
    bus.set_connection("n8n", True)
    bus.set_machine("laptop")

    async def loop() -> None:
        while True:
            await _script()

    task = asyncio.create_task(loop())
    try:
        await run_hud(port)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
