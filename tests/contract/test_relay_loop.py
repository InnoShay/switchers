"""RS-10 regression: a mirrored plan that mentions an offline agent must not start a loop.

Live incident: the relay mirrored a plan containing `@hands ...` into both HQ rooms, Switch
auto-replied as the offline desk-laptop, the desk parsed that auto-reply as a command,
answered `didn't understand ... try: @hands help`, which Switch auto-replied to again, forever.
"""

import asyncio

from roomservice.agents.backup import BackupAgent
from tests.contract.fake_switch import FakeSwitch, message_frame, sleep
from tests.contract.test_roles_handoff import make, setup_fake, wait_for

OFFLINE = (
    "@desk-backup I'm currently offline — my connector isn't reporting in. "
    "I'll respond once it reconnects."
)
ROOMS = [
    {"id": "hq-1", "name": "roomservice-hq"},
    {"id": "hq-2", "name": "Telegram: RoomService HQ"},
    {"id": "m-1", "name": "mission-a"},
]


def offline_reply(body: str) -> str | None:
    """Switch answers any post that mentions an agent with an offline connector."""
    return OFFLINE if ("@hands" in body or "@desk-" in body) else None


def posts(fake) -> list[str]:
    op = [c["args"]["body"] for c in fake.calls_named("op:post_message")]
    return op + [c["body"]["content"] for c in fake.calls_named("message")]


async def test_mirrored_plan_with_mention_does_not_loop(fixtures_dir, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    plan = message_frame(
        1, "plan:\n@hands shot page", addressed=False, room_id="m-1", sender_name="concierge"
    )
    fake = await FakeSwitch(
        {"m-1": [sleep(0.8), plan]}, rooms=ROOMS, auto_reply=offline_reply
    ).start()
    setup_fake(fake, monkeypatch, "desk-backup")
    agent = make(BackupAgent, fixtures_dir, "desk-backup")
    try:
        await agent.start()
        await wait_for(lambda: agent.watcher.room("m-1") is not None)
        ok, _ = await agent.assume_hands(agent.watcher.room("m-1"))  # backup holds hands
        assert ok
        await wait_for(lambda: len(posts(fake)) >= 1, 5)
        await asyncio.sleep(3.0)
        out = posts(fake)
        assert len(out) < 10, out
        # nothing mirrored may carry a live mention
        assert not any("@hands" in b for b in out)
    finally:
        await agent.stop()
        await fake.stop()


async def test_hq_auto_reply_is_ignored(fixtures_dir, monkeypatch, tmp_path):
    """An auto-reply that arrives in HQ addressed to the desk is never answered."""
    monkeypatch.chdir(tmp_path)
    reply = message_frame(
        1, OFFLINE, room_id="hq-1", sender="@laptop:srv", sender_name="desk-laptop"
    )
    reply["send"]["data"]["payload"]["com.switch.auto_reply"] = True
    fake = await FakeSwitch({"hq-1": [reply]}, rooms=ROOMS, auto_reply=offline_reply).start()
    setup_fake(fake, monkeypatch, "desk-backup")
    agent = make(BackupAgent, fixtures_dir, "desk-backup")
    try:
        await agent.start()
        await asyncio.sleep(1.5)
        assert posts(fake) == []
    finally:
        await agent.stop()
        await fake.stop()
