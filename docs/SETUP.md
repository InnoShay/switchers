# Setup from scratch

Everything below was done on a clean macOS machine. Linux works the same; for Windows use `scripts/setup_windows.ps1` and the same Switch steps.

## What you need

| Tool | Why | Install |
|---|---|---|
| Git | clone the repo | `brew install git` |
| [uv](https://docs.astral.sh/uv/) | Python 3.12 and dependencies | `brew install uv` |
| Node 20+ | the demo project (`demo/volt`) | `brew install node` |
| Docker Desktop | the local Switch server and Mattermost | [docker.com](https://www.docker.com/products/docker-desktop), then open it once |
| [Switch Console](https://switchagents.ai) (0.40 or newer) | runs the Planner, Builder and Researcher agents | download from the Switch site |
| An agent provider signed in | the three Console agents need one | for example `claude auth login` |
| VS Code with the `code` command | the desk opens your editor | VS Code, then Cmd+Shift+P "Shell Command: Install 'code' command in PATH" |
| Telegram (optional) | drive the room from your phone | a bot from `@BotFather` |

## 1. Clone and bootstrap

```bash
git clone https://github.com/InnoShay/switchers.git
cd switchers
bash scripts/bootstrap.sh
```

This installs the Python dependencies, creates `~/roomservice-workspace` with the demo project, starts a local Switch server (Docker Compose, with Mattermost and the admin Gateway), writes `SWITCH_URL` into `.env` and runs `uv run roomservice doctor`.

Check the server answers: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health` prints `200`.

## 2. Grant the macOS permissions (once)

System Settings, Privacy & Security, **Screen Recording**: enable your terminal app, then quit and reopen it. Create two shortcuts in the Shortcuts app named `RoomService Focus On` and `RoomService Focus Off` (action: Set Focus, Do Not Disturb on/off). Click OK on the Automation prompt the first time a terminal opens.

## 3. Create the registration key

The registration key lets RoomService register its own agents (`desk-laptop`, `life`).

1. Open the Gateway at <http://127.0.0.1:3000> and sign in as `admin@switch.local`. The password is in `~/switch-server/.env`; copy it without printing it:
   ```bash
   grep ^GATEWAY_ADMIN_PASSWORD ~/switch-server/.env | cut -d= -f2 | pbcopy
   ```
2. Open **API Keys**, then **Create Registration Key**, label it `roomservice`, and copy the key (it is shown once).
3. Put it in `.env` as `SWITCH_REGISTRATION_KEY=...`.

## 4. Register the desk agents

```bash
uv run roomservice register          # desk-laptop and life
uv run roomservice register --agent desk-backup   # optional, for the handoff demo
```

A yellow "could not set addressing" line is normal on Switch 0.31; the keys are saved in `~/.roomservice/agents.json`.

## 5. Connect Switch Console

In Console choose **Connect to an existing server**, address `http://127.0.0.1:8000`, sign in as `admin@switch.local`. Home should list Mattermost under Messaging apps.

## 6. Import the team template

Templates, **Import template**, load `switch/templates/dist/roomservice-crew.template.yaml` and run it. **Set Workspace folder to the absolute path** `/Users/<you>/roomservice-workspace` (Console does not expand `~`). This creates the Planner, Builder and Researcher and the main chat room `roomservice-hq`. The Planner posts a three-line introduction when it works.

## 7. Import the task template

Import `switch/templates/dist/roomservice-mission.template.yaml` the same way (do not run it; the Planner runs it for every task) and make it visible to the workspace.

## 8. Set the three Console agents

For Planner, Builder and Researcher: **Who can talk to your agent** is "Me and my agents", **Auto mode** on. For the Builder turn **Bypass permissions** on: with it off, Switch cannot show the Builder's permission cards and the Builder waits forever.

## 9. Room commands

Sign in to Mattermost at <http://127.0.0.1:8065> (user `user`, team `switch`; password: `grep ^MATTERMOST_USER_PASSWORD ~/switch-server/.env | cut -d= -f2 | pbcopy`). In `roomservice-hq`, one message each:

```
!assign-agent @concierge
!set-alias @desk-laptop @computer
```

Press Esc to close Mattermost's autocomplete before sending so it does not rewrite the names.

## 10. Telegram main chat (optional)

1. In Telegram: `@BotFather`, `/newbot`, then `/mybots`, Bot Settings, **Group Privacy, Turn off** (before adding the bot to a group).
2. Console, Home, Messaging apps, Connect, Telegram: paste the token and the bot username.
3. Create a group `RoomService HQ`, add the bot, send one message, then link your account when Console asks (search your Telegram `@username`).
4. In the group, one per message: `!invite-agent @concierge`, `!invite-agent @desk-laptop`, `!invite-agent @life`, `!assign-agent @concierge`, `!set-alias @desk-laptop @computer`.
5. Switch names the room `Telegram: RoomService HQ`. Add that exact name to `ROOMSERVICE_HQ_ROOMS` in `.env`:
   `ROOMSERVICE_HQ_ROOMS=roomservice-hq,RoomService HQ,Telegram: RoomService HQ`.

## 11. Pair yourself as the owner

```bash
uv run roomservice pair      # prints a 6-digit code, valid 10 minutes
```

From each surface (Mattermost and Telegram) post in the main chat: `@computer pair 123456`. The Computer answers `paired`. Only paired accounts can wake the desk, approve with `ok CODE` and pause it.

## 12. Run it

```bash
bash scripts/demo_up.sh      # Docker, Switch, n8n if configured, doctor, the desk and the HUD
```

The HUD opens at <http://127.0.0.1:7777>. From your phone, say "Room service, tonight we ship the Volt waitlist page". Then try `@computer status`, `@computer projects`, "show me" and "make the join button orange".

## Optional

- **Calendar and email (the Assistant)**: `n8n/README.md`.
- **Backup computer**: `ROOMSERVICE_AGENT=desk-backup ROOMSERVICE_DESK_CONFIG=config/desk.backup.yaml HUD_PORT=7778 uv run roomservice backup` (copy `config/desk.yaml` to `config/desk.backup.yaml` and set `machine_name: backup`). Stop the main desk and the backup takes over within about 15 seconds.
- **Open any project, run anything with approval**: `docs/power.md`. Set `ROOMSERVICE_PROJECTS_DIR` to your projects folder.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `doctor` shows "Owners paired: none" | run step 11 |
| Template import: `ENOENT mkdir '~'` | use the absolute workspace path in step 6 |
| `!assign-agent` says "isn't switched on" | the server needs `FEATURE_FLAGS_ENABLED=follow_the_conversation` (the setup script sets it); then `docker compose up -d` in `~/switch-server` |
| The Telegram group is not treated as the main chat | add its exact name to `ROOMSERVICE_HQ_ROOMS` (step 10.5) |
| Builder never answers | turn Bypass permissions on, then `!interrupt @builder` and `!reset @builder` |
| Screenshots are black | Screen Recording permission (step 2), restart the terminal |
| `spike s2`/`register` 403 on addressing | harmless on Switch 0.31 |
| Everything is quiet after a restart | the desk takes the `hands` role again on the next `@desk-laptop task <slug> <project>` |
