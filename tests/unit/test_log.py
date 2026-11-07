import json
import logging

import pytest

from roomservice import log, store


@pytest.mark.parametrize(
    "raw,secret",
    [
        ("Authorization: Bearer abc123.def", "abc123.def"),
        ("headers={'Authorization': 'Bearer sk-live-999'}", "sk-live-999"),
        ('{"api_key": "k-very-secret"}', "k-very-secret"),
        ("api_key=k-very-secret more", "k-very-secret"),
        ("token=tok_123", "tok_123"),
        ("calling with bearer ZZZ.yyy.xxx now", "ZZZ.yyy.xxx"),
    ],
)
def test_redact(raw, secret):
    out = log.redact(raw)
    assert secret not in out
    assert "[REDACTED]" in out


def test_clip_limits_to_400():
    assert len(log.clip("a" * 1000)) == 400
    assert log.clip("short") == "short"


def test_jsonl_output_is_redacted_and_clipped(rs_home):
    log.reset_logging()
    logger = log.setup_logging(console=False)
    child = log.get_logger("desk")
    child.info("auth Authorization: Bearer SECRETVALUE %s", "x" * 600,
               extra={"agent": "desk-laptop", "room": "r1", "event": "test"})  # fmt: skip
    for h in logger.handlers:
        h.flush()
    lines = (store.logs_dir() / "runtime.jsonl").read_text().splitlines()
    rec = json.loads(lines[-1])
    assert set(rec) == {"ts", "level", "agent", "room", "event", "msg"}
    assert rec["agent"] == "desk-laptop" and rec["room"] == "r1" and rec["event"] == "test"
    assert "SECRETVALUE" not in rec["msg"]
    assert len(rec["msg"]) <= 400
    assert rec["level"] == "info"
    log.reset_logging()
    assert logging.getLogger("roomservice").handlers == []
