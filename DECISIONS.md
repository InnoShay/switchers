# Decisions

One line per decision: `RS-XX: decision — reason`. Spike results (S0–S8) go here too.

RS-01: scripts/tickets.sh avoids bash-4 associative arrays (uses a `case` lookup) — macOS ships bash 3.2 and `declare -A` fails there.
RS-01: Settings uses pydantic-settings `NoDecode` + a validator for ROOMSERVICE_HQ_ROOMS — the spec wants a comma-separated .env value, not JSON.
RS-01: Settings sets `env_ignore_empty=True` — .env.example ships empty values (e.g. LIGHTS_ON_URL=) that must mean "unset".
RS-01: ProtocolAgent.start/stop/reply/upload/hq_rooms raise NotImplementedError and only on_message is abstract — the spec marks only on_message abstract and gives no bodies for the rest.
RS-01: contracts/os.py `get_adapter` delegates lazily to `roomservice.desk.os.get_adapter` (built in RS-07) — keeps the contract signature without a circular import.
RS-01: Bus gained `set_connection()` and `set_machine()` helpers (additive) — the snapshot needs switch/n8n connection state, which no HUD event carries.
RS-01: MessageEvent.body is truncated to 400 chars (with "…") rather than rejected — a long chat message must never crash a publisher.
RS-01: CODEOWNERS handles: Lakshay = @InnoShay (gh api user), Yash = @yash-144 (confirmed by Lakshay).
RS-01: ruff format excludes *.md — newer ruff reformats the Python code blocks inside SPEC.md, which must stay byte-identical.
RS-03: list_rooms result parsed tolerantly (list, or dict wrapping `rooms`; ids from `id`/`room_id`) — Appendix A gives no response shape; confirm with S2/S3 on the real server.
RS-03: RoomConnection also skips frames with id <= last enqueued id (not only <= cursor) — cursor advances after the handler, so a resume could otherwise re-enqueue an in-flight event.
RS-03: connection_state only seeds the cursor when none is stored — overwriting it could skip events still queued.
RS-03: connect_to_room runs right after the first connection_state frame, off the receive task — keeps pongs immediate; handler waits for it so self-id is known.
RS-03: `refused` with 4xx (except 408/429) and close code 4400 are fatal for that room; other refusals reconnect with backoff — spec only says "log; close".
RS-03: paired-owner ids are read from every "sender" key in owners.json — RS-07 owns the file format; this only feeds the HUD `you` label.
RS-03: added python-multipart to the dev dependency group — FastAPI form/file parsing in tests/contract/fake_switch.py.
