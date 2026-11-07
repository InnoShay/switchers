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
