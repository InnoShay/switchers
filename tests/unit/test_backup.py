"""desk-backup poll logic and S8 timing (SPEC §15, §20.1). Pure logic; no network."""

from roomservice.agents.backup import newest_mission
from roomservice.contracts.agent import RoomInfo, RoomKind
from roomservice.spikes import LEASE_PASS_S, LapseMeter, recommend_mode


def room(i, name, kind=RoomKind.MISSION):
    return RoomInfo(id=i, name=name, kind=kind)


def test_newest_mission_prefers_latest_activity_then_list_order():
    rooms = [room("a", "mission-a"), room("b", "mission-b"), room("h", "hq", RoomKind.HQ)]
    raw = [
        {"id": "a", "updated_at": 9},
        {"id": "b", "updated_at": 5},
        {"id": "h", "updated_at": 99},
    ]
    assert newest_mission(rooms, raw).id == "a"
    raw = [{"id": "a"}, {"id": "b"}]  # no timestamps: later in the list wins
    assert newest_mission(rooms, raw).id == "b"
    assert newest_mission([room("h", "hq", RoomKind.HQ)], [{"id": "h"}]) is None


def test_lapse_meter_times_from_kill_to_holder_change():
    m = LapseMeter()
    m.observe(0.0, None)
    m.observe(1.0, "desk-laptop")
    m.observe(2.0, "desk-laptop")
    m.kill(3.0)
    m.observe(4.0, "desk-laptop")
    assert m.lapse_s is None
    m.observe(11.5, "desk-backup")
    m.observe(12.5, "desk-backup")
    assert m.lapse_s == 8.5 and m.new_holder == "desk-backup"


def test_lapse_meter_counts_unheld_as_lapse():
    m = LapseMeter()
    m.observe(0, "desk-laptop")
    m.kill(1)
    m.observe(20, None)
    assert m.lapse_s == 19


def test_recommend_mode_threshold():
    assert LEASE_PASS_S == 15.0
    assert recommend_mode(8.5) == "lease"
    assert recommend_mode(15.0) == "lease"
    assert recommend_mode(15.1) == "explicit"
    assert recommend_mode(None) == "explicit"


def test_rs07_task_prefix_is_a_task_room_and_old_prefix_still_works():
    from roomservice.switch.rooms import detect_kind

    assert detect_kind("x", "task-volt", ["roomservice-hq"]) == RoomKind.MISSION
    assert detect_kind("x", "Task-Volt", []) == RoomKind.MISSION
    assert detect_kind("x", "mission-volt", []) == RoomKind.MISSION
    assert detect_kind("x", "roomservice-hq", ["roomservice-hq"]) == RoomKind.HQ
    assert detect_kind("x", "random", []) == RoomKind.OTHER
