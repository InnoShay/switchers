from datetime import UTC, datetime

from roomservice.desk import receipts as r


def test_ok_with_args():
    assert (
        r.ok("boot", ["volt"], "editor, 1 terminal, 2 tabs, focus, music", 3.44)
        == "✅ boot volt · editor, 1 terminal, 2 tabs, focus, music · 3.4s"
    )


def test_ok_no_args():
    assert r.ok("wrap", [], "saved", 0.05) == "✅ wrap · saved · 0.1s"


def test_ok_quotes_args_with_spaces():
    assert r.ok("commit", ["waitlist page v1"], "abc123", 1.0) == (
        '✅ commit "waitlist page v1" · abc123 · 1.0s'
    )


def test_seconds_one_decimal():
    assert r.fmt_seconds(12) == "12.0s"
    assert r.fmt_seconds(0.04) == "0.0s"
    assert r.fmt_seconds(9.96) == "10.0s"


def test_queued():
    assert r.queued("shot", "boot volt") == "⏳ queued · shot (busy with boot volt)"


def test_refused_allowlist():
    assert (
        r.refused("open Steam", "not on the allowlist")
        == "⛔ refused · open Steam — not on the allowlist"
    )


def test_refused_variants():
    assert r.refused_too_many() == "⛔ refused · more than 5 commands in one message"
    assert r.refused_rate_limit() == "⛔ refused · rate limit (20/min)"
    assert r.refused_frozen() == "⛔ refused · frozen by owner"


def test_didnt_understand():
    assert (
        r.didnt_understand("make it orange")
        == '⛔ didn\'t understand · "make it orange" · try: @hands help'
    )


def test_approval_needed_exact():
    assert r.approval_needed('commit "waitlist page v1"', "volt", "K7Q3") == (
        '⚠️ approval needed · commit "waitlist page v1" in volt\n'
        "Owner: reply  ok K7Q3  or  no K7Q3  (5 min)"
    )


def test_approval_needed_without_project_and_ttl():
    assert r.approval_needed("close all", None, "AC34", ttl_s=120) == (
        "⚠️ approval needed · close all\nOwner: reply  ok AC34  or  no AC34  (2 min)"
    )


def test_approved():
    assert (
        r.approved("Lakshay", "commit 3f2a91c", 1.26)
        == "✅ approved by Lakshay · commit 3f2a91c · 1.3s"
    )


def test_declined():
    assert r.declined("Lakshay", "push") == "🚫 declined by Lakshay · push"


def test_expired():
    assert r.expired("K7Q3", "push") == "⌛ expired · K7Q3 · push"


def test_screenshot_caption_project_and_screen():
    when = datetime(2026, 11, 7, 14, 32, 1, tzinfo=r.IST)
    assert r.screenshot_caption("volt", "http://localhost:5173", when) == (
        "📸 volt · http://localhost:5173 · 14:32 IST"
    )
    assert r.screenshot_caption("screen", None, when) == "📸 screen · screen · 14:32 IST"


def test_screenshot_caption_converts_to_ist():
    when = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
    assert r.screenshot_caption("screen", None, when).endswith("· 14:30 IST")


def test_ignition_hands_paired_freeze():
    assert r.ignition("volt") == "⚡ ignition · booting volt"
    assert r.ignition("focus-session") == "⚡ ignition · booting focus-session"
    assert r.hands_now_on("desk-backup") == "🫱 hands is now on desk-backup"
    assert r.paired("Lakshay", "RoomService HQ") == "🔐 paired · Lakshay on RoomService HQ"
    assert r.frozen("Lakshay") == "🧊 frozen by Lakshay"
    assert r.unfrozen("Lakshay") == "🔥 unfrozen by Lakshay"


def test_wrap_receipt_shape():
    state = {"slug": "volt-waitlist", "mission_minutes": 96}
    assert r.wrap("volt-waitlist", 96, state) == (
        "✅ wrap · volt-waitlist · 96 min\n```json\n"
        '{"slug":"volt-waitlist","mission_minutes":96}\n```'
    )


def test_resume_receipts():
    assert (
        r.resume("volt", "editor, 1 terminal, 2 tabs", "3f2a91c")
        == "✅ resume volt · editor, 1 terminal, 2 tabs · last head 3f2a91c"
    )
    assert r.resume("volt", "editor", no_state=True) == "✅ resume volt · editor · no saved state"


def test_mission_already_booted():
    assert (
        r.mission_already_booted("volt-waitlist")
        == "✅ mission volt-waitlist · already booted · hands assumed"
    )
