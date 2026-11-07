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
RS-05: grammar returns a ParsedMessage (items + refusal) and reports unknown verbs as ParseError — the spec only gives Command/ParseError; extras beyond 5 are dropped with the exact refusal text so the first 5 still run.
RS-05: "show me" parses to `shot` with the trailing "me" dropped — `show` is an alias of `shot` and the golden path says "show me".
RS-05: allowlist denial reason is `not on the allowlist` (A13 text is `⛔ refused · <raw> — <reason>`); disallowed URLs say `url not allowed (https or localhost only)`; alias URLs from desk.yaml also pass the URL pattern rule.
RS-05: Approvals.resolve takes `owner_ids` and `is_agent` from the caller (agent layer knows pairing/identity) and returns None for non-owners/agents, `unknown` for unmatched codes; codes use secrets.choice and a late-bound time.time so freezegun works.
RS-05: auto-wrap on a new mission keeps the booted set (apps remain open); only explicit `wrap` or `close all` clears it. Wrap `path` is written with `~` for the home dir, as in the §12.8 example; mission slugs must match `[A-Za-z0-9][A-Za-z0-9_-]*` (they become filenames).
