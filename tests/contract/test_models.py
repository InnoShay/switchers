"""Round-trip tests for the frozen Switch / agent / OS contract models."""

import pytest
from pydantic import ValidationError

from roomservice.contracts.agent import ProtocolAgent, RoomInfo, RoomKind
from roomservice.contracts.os import RunResult
from roomservice.contracts.switch import DomainEvent, MessagePayload, OpError


def test_domain_event_from_frame():
    frame = {
        "event": "message",
        "id": 42,
        "data": {
            "type": "message",
            "room_id": "r1",
            "bridge_id": None,
            "channel_type": "channel_public",
            "payload": {
                "addressed": True,
                "sender": "@switch-user-1:srv",
                "sender_name": "Lakshay",
                "message_id": "m1",
                "body": "@hands status",
                "timestamp": 1730000000000,
            },
            "sequence": 42,
        },
    }
    ev = DomainEvent.model_validate(frame["data"])
    msg = MessagePayload.model_validate(ev.payload)
    assert ev.sequence == 42 and msg.addressed and msg.thread_id is None and msg.attachments == []
    assert DomainEvent.model_validate_json(ev.model_dump_json()) == ev
    assert MessagePayload.model_validate_json(msg.model_dump_json()) == msg


def test_domain_event_rejects_unknown_type():
    with pytest.raises(ValidationError):
        DomainEvent(type="bogus", room_id="r", payload={}, sequence=1)


def test_op_error_carries_status_and_detail():
    e = OpError(409, "exists")
    assert (e.status, e.detail) == (409, "exists")
    assert "409" in str(e)


def test_room_info_and_kind():
    r = RoomInfo(id="r1", name="mission-x", kind=RoomKind.MISSION)
    assert r.conn_id is None
    assert RoomInfo.model_validate_json(r.model_dump_json()) == r
    assert RoomKind("hq") is RoomKind.HQ


def test_protocol_agent_requires_on_message():
    with pytest.raises(TypeError):
        ProtocolAgent()  # type: ignore[abstract]

    class A(ProtocolAgent):
        name = "a"

        async def on_message(self, room, ev, msg): ...

    assert A().name == "a"


def test_run_result_round_trip():
    r = RunResult(code=0, stdout_tail="ok", stderr_tail="", ms=12)
    assert RunResult.model_validate_json(r.model_dump_json()) == r


def test_contract_modules_import():
    import roomservice.contracts.config  # noqa: F401
    import roomservice.contracts.events  # noqa: F401
