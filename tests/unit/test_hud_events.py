import pytest

from roomservice.contracts.events import (
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
    dump_event,
    parse_event,
)

SAMPLES = [
    HelloEvent(
        mission=None,
        crew=[CrewMember(name="hands", color="#FF5C7A", state="idle")],
        connections=Connections(switch=True, n8n=False),
        machine="laptop",
    ),
    IgnitionEvent(project="volt", lights="flash"),
    MissionEvent(slug="volt-waitlist", title="Volt waitlist", started_at=1),
    MessageEvent(
        room="mission-volt-waitlist",
        room_kind="mission",
        sender_name="Builder",
        agent="builder",
        body="hi",
        addressed=True,
    ),
    AgentStateEvent(agent="builder", state="working"),
    ActionStartEvent(id="a1", verb="boot", args=["volt"], room="roomservice-hq"),
    ActionEndEvent(id="a1", ok=True, ms=3400, summary="editor, 1 terminal"),
    ApprovalOpenEvent(code="K7Q3", cmd='commit "x"', expires_at=2),
    ApprovalClosedEvent(code="K7Q3", result="ok", by="Lakshay"),
    ScreenshotEvent(url="/shots/shot-volt-143201.png", caption="📸"),
    SpeakEvent(text="Evening."),
    TransferEvent(from_agent="desk-laptop", to_agent="desk-backup"),
    FreezeEvent(on=True),
    SystemEvent(level="warn", text="room opened"),
]


@pytest.mark.parametrize("ev", SAMPLES, ids=lambda e: e.type)
def test_round_trip(ev):
    again = parse_event(dump_event(ev))
    assert type(again) is type(ev)
    assert again == ev
    assert isinstance(again.ts, int)


def test_every_spec_type_is_covered():
    assert {e.type for e in SAMPLES} == {
        "hello", "ignition", "mission", "message", "agent_state", "action_start",
        "action_end", "approval_open", "approval_closed", "screenshot", "speak",
        "transfer", "freeze", "system",
    }  # fmt: skip


def test_message_body_is_capped_at_400():
    ev = MessageEvent(
        room="r", room_kind="hq", sender_name="x", agent="you", body="a" * 900, addressed=False
    )
    assert len(ev.body) == 400


def test_unknown_type_rejected():
    with pytest.raises(ValueError):
        parse_event({"type": "nope", "ts": 1})
