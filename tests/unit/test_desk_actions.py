"""Verbs, pairing and safety rules of the DeskAgent (SPEC §9.5, §12.3, §17)."""

from roomservice import store
from roomservice.agents.desk import load_owners, new_pairing_code
from tests.unit.test_desk_queue import HQ, desk, posts, say  # noqa: F401


async def test_pairing_flow_stores_owner_and_replies(desk):  # noqa: F811
    code = new_pairing_code()
    await say(desk, f"@hands pair {code}", sender="@new:srv", name="Lakshay")
    assert posts(desk)[-1] == "🔐 paired · Lakshay on roomservice-hq"
    assert {"sender": "@new:srv", "sender_name": "Lakshay", "room_name": "roomservice-hq"} in (
        load_owners()
    )


async def test_pairing_rejects_bad_code_agents_and_non_hq(desk):  # noqa: F811
    new_pairing_code()
    await say(desk, "@hands pair 000000", sender="@x:srv", name="x")
    assert posts(desk)[-1].startswith("⛔ refused · pair — bad or expired")
    code = store.read_json(store.home() / "pairing.json")["code"]
    await say(desk, f"@hands pair {code}", sender="@bot:srv", name="builder")
    assert posts(desk)[-1] == "⛔ refused · pair — agents cannot pair"
    assert all(o["sender"] != "@bot:srv" for o in load_owners())


async def test_agents_cannot_resolve_approvals(desk):  # noqa: F811
    await say(desk, "@hands boot volt")
    await desk.drain()
    await say(desk, "@hands push")
    await desk.drain()
    code = next(p for p in posts(desk) if "approval needed" in p).split("ok ")[1].split()[0]
    await say(desk, f"ok {code}", sender="@bot:srv", name="builder")
    await desk.drain()
    assert not any(p.startswith("✅ approved") for p in posts(desk))
    assert desk.approvals.get(code) is not None


async def test_push_never_takes_force_and_unknown_things_refused(desk):  # noqa: F811
    await say(desk, "@hands boot volt")
    await say(desk, "@hands push --force")
    await say(desk, "@hands open nope")
    await say(desk, "@hands url file:///etc/passwd")
    await say(desk, "@hands url http://example.com")
    await say(desk, "@hands run nope")
    await desk.drain()
    p = posts(desk)
    assert "⛔ refused · push --force — push takes no arguments (never forced)" in p
    assert "⛔ refused · open nope — not on the allowlist" in p
    assert sum(x.startswith("⛔ refused · url ") for x in p) == 2
    assert "⛔ refused · run nope — not on the allowlist" in p


async def test_wrap_and_resume_roundtrip(desk):  # noqa: F811
    await say(desk, "@hands mission volt-waitlist volt")
    await desk.drain()
    await say(desk, "@hands wrap")
    await say(desk, "@hands resume volt")
    await desk.drain()
    p = posts(desk)
    wrap = next(x for x in p if x.startswith("✅ wrap · volt-waitlist"))
    assert '"slug":"volt-waitlist"' in wrap
    assert any(x.startswith("✅ resume volt") and "no saved state" not in x for x in p)


async def test_shot_in_dry_run_uploads_png(desk):  # noqa: F811
    uploads = []

    async def fake_upload(room, png, filename, caption, thread_id=None):
        uploads.append((filename, caption, png[:4]))

    desk.upload = fake_upload
    await say(desk, "@hands shot screen")
    await desk.drain()
    name, caption, magic = uploads[0]
    assert name.startswith("shot-screen-") and name.endswith(".png")
    assert caption.startswith("📸 screen · screen · ") and caption.endswith(" IST")
    assert magic == b"\x89PNG"
    assert (store.shots_dir() / name).exists()
    assert HQ.name == "roomservice-hq"
