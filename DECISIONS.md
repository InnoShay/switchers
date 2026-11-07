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
RS-05: grammar returns a ParsedMessage (items + refusal) and reports unknown verbs as ParseError — the spec only gives Command/ParseError; extras beyond 5 are dropped with the exact refusal text so the first 5 still run.
RS-05: "show me" parses to `shot` with the trailing "me" dropped — `show` is an alias of `shot` and the golden path says "show me".
RS-05: allowlist denial reason is `not on the allowlist` (A13 text is `⛔ refused · <raw> — <reason>`); disallowed URLs say `url not allowed (https or localhost only)`; alias URLs from desk.yaml also pass the URL pattern rule.
RS-05: Approvals.resolve takes `owner_ids` and `is_agent` from the caller (agent layer knows pairing/identity) and returns None for non-owners/agents, `unknown` for unmatched codes; codes use secrets.choice and a late-bound time.time so freezegun works.
RS-05: auto-wrap on a new mission keeps the booted set (apps remain open); only explicit `wrap` or `close all` clears it. Wrap `path` is written with `~` for the home dir, as in the §12.8 example; mission slugs must match `[A-Za-z0-9][A-Za-z0-9_-]*` (they become filenames).
RS-07: owners.json is a list of `{sender, sender_name, room_name}` (one entry per paired surface); the pairing code lives in `~/.roomservice/pairing.json` (mode 600, 10 min) so `roomservice pair` and `up` (separate processes) share it; the code stays valid for the second surface until expiry; 5 bad codes burn it; pairing only works from an HQ room.
RS-07: control verbs (`ok`/`no`/`freeze`/`unfreeze`/`pair`) run immediately, outside the serial queue, so freeze can preempt a busy desk; everything else is queued. Rate limit counts accepted commands (checked at submit); frozen is checked at submit and again when a queued job starts.
RS-07: a failed or invalid command is posted as `⛔ refused · <raw> — <reason>` (no other failure format exists); `run` with exit != 0 posts `⚠️ run <key> · exit N` plus the last 15 lines in a fenced block.
RS-07: approval results (`✅ approved by`, `🚫 declined by`) post in the requesting room and also in the room where the owner answered, so the phone sees the outcome; `⌛ expired` posts in the requesting room.
RS-07: lights webhook is a plain GET; skipped in dry-run. `wait_for` is skipped in dry-run. Boot skips the lights step if ignition fired within 60 s.
RS-07: boot also accepts a profile name (ignition's `default_profile`); profile receipt lists `N apps, N tabs, focus, music`.
RS-07: `shot page` calls `desk.actions.capture_page` (returns None until RS-10 fills it) and falls back to the screen with ` (screen fallback)`; PNGs are saved to ~/.roomservice/shots/shot-<label>-HHMMSS.png for the HUD.
RS-07: registration-key doctor check only verifies the key is set (no side-effect-free validation endpoint exists); Linux `open_app`/`open_terminal` use asyncio.create_subprocess_exec detached instead of Popen so every adapter shares one mockable entry point.
RS-07: `up` calls Yash's optional `run_hud`, `LifeAgent`, `start_scheduler` with only the keyword arguments their signatures accept (port/settings/cfg/desk/agent); he can adjust signatures freely. Lease renewal (RS-12) is the empty `DeskAgent.start_lease_renewal` stub.
RS-10: decision — plan mirror is the header line plus the concierge's first 5 non-empty lines, because §13.4 caps every HQ message at 6 lines (§13.2 says "first 6 lines").
RS-10: decision — the kickoff (skipped for the plan rule) is a concierge message matching `@desk…/@hands … mission <slug>`; the next concierge message in that mission room is the plan, mirrored once.
RS-10: decision — the base class drops the desk's own messages, so desk screenshots, `⚠️ approval needed` and `✅ wrap` are mirrored from DeskAgent.reply()/upload() overrides (mission rooms only); wrap mirror uses the room name and the minutes parsed from the receipt.
RS-10: decision — `… +N updates in mission-<slug>` goes out once the oldest suppressed mirror is 60 s old (checked on each mirror and by the desk's 5-s sweeper), and does not count against the 6/min budget.
RS-10: decision — builder permission detection uses the literal phrases `Allow once|Allow for this session` (relay.PERMISSION_RE) until Yash's tests/fixtures/permission_request.json (S5) finalizes it; approval answer receipts: `✅ approved by … · builder answered yes` / `🚫 declined by …` in the owner's room.
RS-10: decision — `capture_page` lives in desk/pageshot.py and is imported into desk/actions.py under the same name; failures log and return None (caller falls back to the screen).
RS-12: mission refusal when hands is held posts exactly `⛔ refused · hands is held by <holder>` (§15 text, no raw command) — receipts.refused_held; ActionResult.text now overrides the refusal receipt.
RS-12: backup picks the newest mission by list_rooms activity timestamp, falling back to list order — the spec says "newest" but list_rooms has no documented ordering.
RS-12: backup uses the desk.yaml from ROOMSERVICE_DESK_CONFIG (point it at a file with `machine_name: backup`) and disables ignition and unaddressed approval handling until it holds hands — avoids double ignition/"no open approval" noise next to the laptop.
RS-12: lease mode tries assume_role every 5 s even while hands is shown held (409 = lease alive); explicit mode only assumes when list_roles shows hands unheld.
RS-12: S8 spike measures from the moment the operator presses Enter after killing the laptop runtime to the first list_roles holder change, and prints the recommended ROOMSERVICE_HANDOFF_MODE; it runs as rs-spike to avoid stealing a desk connection. Real timing still to be recorded.
RS-14: decision — registration-key doctor check stays "key is set": Appendix A documents no side-effect-free endpoint (POST /agents always creates or overwrites), so no real validity probe is added; agent keys are proven by `GET /ops`.
RS-14: bug fix — Windows `open_url` used `cmd /c start "" <url>`, so `https://x.com&calc` would run `calc` (cmd treats `&|^` as separators; the URL rule allows them in query strings). It now uses `rundll32 url.dll,FileProtocolHandler <url>`, which never goes through cmd.
RS-14: bug fix — Windows `speak` only doubled ASCII `'`, but PowerShell also treats the typographic quotes U+2018/2019/201A/201B as string delimiters, so `say "x’; calc; ‘"` broke out of the string. All four are now doubled.
RS-14: bug fix — doctor `non_dark_fraction` used Pillow's deprecated `getdata()` (removed in Pillow 14); it now reads `tobytes()`. `rooms visible` now reports a Switch error as a ❌ with a fix instead of the generic crash line.
RS-14: decision — A12 at the desk level: `close all` is not owner-only in §12.3 (it needs an approval), so a stranger's `close all` that somehow reaches the desk only opens an approval that no non-owner can resolve; `ok/no/freeze/unfreeze` from non-owners are refused `owner only`. Tested, not changed.
RS-14: decision — chaos tests scale the 20 s Wi-Fi outage to 3 s (reconnect backoff caps at 10 s, same code path); the n8n-down check is skipped until `LifeAgent` exists (agents/life.py is empty on main). Manual §20.6 runs on the demo machine remain: restart Switch mid-mission, Wi-Fi off 20 s, `docker stop` n8n then ask Life something.
RS-14: bug fix (test) — the chaos test asserted the macOS app name "Google Chrome"; the dry adapter resolves app targets per host OS, so on Linux CI it is `google-chrome`. The assertion now uses `agent.actions.app_target("browser")`, and the pre-outage state is awaited by condition, not by timing.
RS-16: decision — ci runs on push to main as well as pull requests — SPEC §26 requires CI green on main and a test badge, which needs runs on main.
