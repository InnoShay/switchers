# Demo script (2:45)

Shot by shot, adapted to what exists in the repo today (SPEC §21). Phone left (30%), desk right (70%) in OBS. Desk shows the Control Room HUD at `http://127.0.0.1:7777` (a live Switch network map) fullscreen, with Mattermost on a second screen or alt-tab. Wispr Flow is on for every spoken line. Commands in `code` are exact.

## Before recording (checklist)

- [ ] `uv run roomservice doctor` is all green (a "Chrome / Spotify missing" line is a known false negative on a Brave-only machine, see DECISIONS.md RS-06).
- [ ] Docker is up: Switch server (`curl -s -o /dev/null -w "%{http_code}" $SWITCH_URL/health` prints `200`) and n8n (`docker ps` shows it; `http://localhost:5678` loads and the workflow is Active).
- [ ] `uv run roomservice up` is running on the demo machine (not `--dry-run`), HUD open fullscreen (`F`), sound unmuted (`M` toggles), captions off (`C` toggles; `?captions` in the URL turns them on).
- [ ] Second terminal ready for the handoff, same Mac: `ROOMSERVICE_DESK_CONFIG=<path to a desk file with machine_name: backup> uv run roomservice backup` (see DECISIONS.md RS-12). Do not start it until the handoff shot.
- [ ] Warm the Planner: send one throwaway message in the main chat (for example "hello") and wait for the reply, so the first real task is not a cold start. Delete or ignore it in the edit.
- [ ] Owner is paired on both surfaces (`@computer pair <code>` from Telegram and Mattermost). `@computer status` answers in the main chat.
- [ ] `~/roomservice-workspace/projects/volt` is clean (`git status`), dev server port 5173 is free, no leftover `task-volt-waitlist` (or old `mission-volt-waitlist`) room from a rehearsal (archive it).
- [ ] Music: Spotify signed in, the playlist in `config/desk.yaml` plays, system volume at a level the mic can pick up under the voice. macOS Focus shortcuts "RoomService Focus On" and "RoomService Focus Off" exist and work (run each once from the Shortcuts app).
- [ ] Voice: `uv run roomservice say "Evening. Booting Volt."` sounds right at the recording volume (voice name and rate are in `config/desk.yaml`).
- [ ] Lights webhook (`LIGHTS_ON_URL`) works, or accept the HUD's light-flash as the stand-in. Room lights dimmed.
- [ ] Phone: Wispr Flow active, Telegram open on `RoomService HQ` (the main chat), Do Not Disturb on, QuickTime or scrcpy mirror running. Notifications from other apps off on both screens.
- [ ] Screen Recording permission granted to the terminal running `roomservice up` (otherwise `shot screen` is black).
- [ ] Record each segment separately as soon as it passes; keep `runtime.jsonl` of each take as proof. If a live segment fails in the final take, use the earlier passing take.
- [ ] If anything is off, `uv run roomservice hud --demo` shows the full HUD story with no Switch (labelled "demo mode"). Use it only as an insert, never as the main take.

## Shots

| Time | Shot | Say / do (exact) | Expected on screen | Check |
|---|---|---|---|---|
| 0:00 | Dark room, phone glow | Caption: "One sentence." | Phone lit, desk dark | none |
| 0:03 | Phone, Wispr active (hold 5 s on the Wispr indicator) | Dictate in the Telegram main chat: "Room service. Tonight we ship the Volt waitlist page. Block nine to eleven and remind me at eleven." | Sentence appears in the main chat group | none |
| 0:08 | Desk | Nothing, hands off keys | Light on or HUD flash, HUD wake-up overlay, voice "Evening. Booting Volt.", VS Code opens Volt, terminal runs the dev server, browser opens `http://localhost:5173`, focus mode on, music starts. `⚡ ignition · booting volt` then `✅ boot volt · ...` in HQ | A1, A2 (first visible within 3 s, receipt within 12 s) |
| 0:20 | HUD, cut to Mattermost | Nothing | `task-volt-waitlist` appears with the team and the `task-brief` document; the HUD lights the path to the new room and the team nodes | A3 (within 75 s) |
| 0:35 | Phone | Nothing | Task card in the main chat, then the `@assistant` reply with the calendar block (a line like `🗓️ blocked 21:00–23:00`) | A7 |
| 0:45 | Mattermost, task room | Type `!roles` | `hands` held by `desk-laptop` (the Computer) | A4 |
| 0:55 | Phone | Dictate: "Show me." | A screenshot of the running Volt page arrives in the main chat with a caption | A5 (within 15 s) |
| 1:05 | Phone | Dictate: "Make the join button orange and bigger, add confetti." | Builder starts in the task room; HUD shows builder active | none |
| 1:10 to 1:40 | Split screen | Let it run. Edit the footage to 4x speed with caption "real time: fill in from the take". When the builder asks permission, `⚠️ approval needed` reaches the phone. Type: `ok K7Q3` using the code shown in that message (the code is generated, `K7Q3` is only an example) | Approval overlay on the HUD (amber), then `✅ approved by ...` in the room, builder continues. If the relay cannot answer the builder (spike S5 fallback), approve on the laptop and say so in the edit | A6, A8 |
| 1:45 | Phone | Nothing | New screenshot of Volt with the orange button, mirrored to the main chat | A6 (within 120 s) |
| 1:55 | Desk | Kill the laptop runtime (Ctrl+C in the `up` terminal) instead of closing the lid, then start `roomservice backup` in the second terminal. If the lease mode is slow, say `@computer release` first | `🫱 hands is now on desk-backup` in the task room and the main chat, spoken "Hands transferred to backup." Check the HUD shows the COMPUTER TRANSFERRED banner: `backup` in this repo runs no HUD of its own, so the banner may only appear on a HUD that is connected to the process that saw the transfer. Verify before recording; if it does not show, rely on the chat line and cut to `hud --demo` for the banner | A9 (within 15 s with lease mode) |
| 2:10 | Phone | Dictate: "Wrap up." then reply `ok` with the code shown | Diary and boot-state documents written in the room, approval for the commit, `✅ wrap` receipt, goodnight spoken, apps close | A10 (within 120 s) |
| 2:30 | HUD | Architecture card (use `docs/architecture.png` as a title insert) | Caption: "Remove Switch and the room has no body, no memory, no leash." | none |
| 2:40 | Title | Caption: "RoomService · built by voice with Wispr Flow · #HowISwitch" | Title card | none |

## Optional inserts (only if time remains)

- Security beat (5 s): in the task room as a non-owner account, `@computer close all`; nothing happens (A12). As the owner, `@computer open Steam` answers `⛔ refused · open Steam — not on the allowlist` (A13).
- Pause beat (5 s): press `S` on the HUD; the Paused banner appears and commands are refused until `unfreeze` (A14).
- Resume beat: "Room service, resume Volt." restores the apps and posts a resume card (A11, within 15 s).

## Notes for the editor

- Captions come from the edit, not from the HUD (the HUD's own captions are for `hud --demo` only).
- Keep one real take for every row of the Checks column; the acceptance runbook is SPEC §20.5 and must pass three times clean before the final recording.
- The HUD shows the room as a network: owner, Switch hub, the main chat and task rooms, the five agents, the Backup computer, n8n and the laptop. Linger on it during 0:20 and 1:55.
