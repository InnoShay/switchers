"""Secrets hygiene (SPEC §17 "Secrets leak", §19): redacted + clipped logs, 600 key files,
`roomservice register` never prints a key."""

from __future__ import annotations

import json
import logging
import stat

import pytest

from roomservice import cli, log, store
from roomservice.switch.http import SwitchHTTPClient
from tests.contract.fake_switch import FakeSwitch

KEY = "sk-SUPER-SECRET-KEY-0123456789"


@pytest.fixture
def jsonl(rs_home):
    log.reset_logging()
    logger = log.setup_logging(level=logging.DEBUG, console=False)
    yield lambda: [
        json.loads(line) for line in (store.logs_dir() / "runtime.jsonl").read_text().splitlines()
    ]
    for h in logger.handlers:
        h.flush()
    log.reset_logging()


@pytest.mark.parametrize(
    "line",
    [
        f"Authorization: Bearer {KEY}",
        f"headers={{'Authorization': 'Bearer {KEY}', 'x': 1}}",
        f'{{"api_key": "{KEY}"}}',
        f"api_key={KEY}",
        f"API-KEY: {KEY}",
        f"token={KEY}",
        f"X-RoomService-Token: {KEY}",
        f"url=http://x/?token={KEY}&a=1",
        f"got bearer {KEY} today",
    ],
)
def test_every_secret_shape_is_redacted(line, jsonl):
    log.get_logger("t").warning(line)
    msg = jsonl()[-1]["msg"]
    assert KEY not in msg and "SUPER-SECRET" not in msg


def test_secrets_are_redacted_in_format_args_and_exceptions(jsonl):
    try:
        raise RuntimeError(f"upstream said api_key={KEY}")
    except RuntimeError as e:
        log.get_logger("t").error("call failed: %s", e)
        log.get_logger("t").error("headers %r", {"Authorization": f"Bearer {KEY}"})
    for rec in jsonl():
        assert KEY not in json.dumps(rec)


def test_long_message_bodies_are_clipped_to_400(jsonl):
    log.get_logger("desk").info("body: %s", "x" * 5000, extra={"agent": "desk", "room": "r"})
    rec = jsonl()[-1]
    assert len(rec["msg"]) <= 400
    assert rec["msg"].endswith("…")


def test_line_has_exactly_the_documented_fields(jsonl):
    log.get_logger("desk").info("hello", extra={"agent": "a", "room": "r", "event": "e"})
    assert set(jsonl()[-1]) == {"ts", "level", "agent", "room", "event", "msg"}


async def test_http_client_never_logs_its_key(jsonl):
    fake = await FakeSwitch().start()
    try:
        c = SwitchHTTPClient(fake.url, agent_id="a1", api_key=KEY)
        await c.health()
        await c.aclose()
        dead = SwitchHTTPClient("http://127.0.0.1:9", agent_id="a1", api_key=KEY)
        with pytest.raises(Exception):  # noqa: B017  (network error after retries)
            await dead.op("list_rooms", {})
        await dead.aclose()
    finally:
        await fake.stop()
    assert KEY not in (store.logs_dir() / "runtime.jsonl").read_text()


def test_agents_json_is_mode_600(rs_home):
    store.save_agent_creds("http://localhost:3000", "desk-laptop", "id1", KEY)
    mode = stat.S_IMODE(store.agents_path().stat().st_mode)
    assert mode == 0o600
    store.save_agent_creds("http://localhost:3000", "life", "id2", KEY)  # rewrite keeps 600
    assert stat.S_IMODE(store.agents_path().stat().st_mode) == 0o600


def test_other_secret_files_are_mode_600(rs_home):
    from roomservice.agents.desk import add_owner, new_pairing_code

    add_owner("@o:srv", "o", "hq")
    new_pairing_code()
    assert stat.S_IMODE(store.owners_path().stat().st_mode) == 0o600
    assert stat.S_IMODE((store.home() / "pairing.json").stat().st_mode) == 0o600


async def test_register_never_prints_keys(monkeypatch, capsys):
    fake = await FakeSwitch().start()
    monkeypatch.setenv("SWITCH_URL", fake.url)
    monkeypatch.setenv("SWITCH_REGISTRATION_KEY", "REG-KEY-SECRET-999")
    try:
        done = await cli._register_all(["desk-laptop", "life"], overwrite=False)
        again = await cli._register_all(["desk-laptop"], overwrite=True)
    finally:
        await fake.stop()
    out = capsys.readouterr()
    text = out.out + out.err
    assert done == ["desk-laptop", "life"] and again == ["desk-laptop"]
    assert "REG-KEY-SECRET-999" not in text
    assert "key-desk-laptop" not in text and "key-life" not in text  # the fake's api keys
    assert "key saved, not shown" in text
    saved = store.load_agent_creds(fake.url, "desk-laptop")
    assert saved and saved["api_key"] == "key-desk-laptop"
