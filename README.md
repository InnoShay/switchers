<div align="center">

# RoomService

**Say one sentence. Your computer wakes up, an AI team takes the job, and nothing risky happens without your say-so.**

[![ci](https://github.com/InnoShay/switchers/actions/workflows/ci.yml/badge.svg)](https://github.com/InnoShay/switchers/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.12-3776ab.svg)](https://www.python.org)
[![built on](https://img.shields.io/badge/built%20on-Switch-111827.svg)](https://switchagents.ai)

[Quick start](#quick-start) · [What it does](#what-it-does) · [How it works](#how-it-works) · [Safety](#safety) · [Docs](#documentation)

![The Control Room: a live map of the Switch room](docs/hud.png)

</div>

RoomService turns a [Switch](https://switchagents.ai) room into something with a body. A small program, the **Computer**, joins your Switch rooms as an agent and acts on your real machine: it opens your project, starts the dev server, screenshots the result, and commits only after you approve. A team of AI agents (**Planner**, **Builder**, **Researcher**) plans and writes the code in a task room, and you steer it all from Telegram or Mattermost.

Everything it does is a message in a Switch room, so it is visible, replayable and approvable from your phone.

## What it does

| You say | What happens |
|---|---|
| "Room service, tonight we ship the Volt page" | The desk wakes (Control Room, spoken greeting), opens the project and dev server. The Planner makes a task room and a plan. |
| "show me" | A screenshot of the running page lands in your chat. |
| "make the join button orange and bigger" | The Builder edits the code; ask again to see it. |
| `@computer boot <any project>` | Finds a folder under your projects directory, detects how to run it, starts it. No config file to edit. |
| `@computer commit "v1"` | `⚠️ approval needed … ok K7Q3`. Nothing runs until you reply with the code. |
| `@computer exec "npm test"` | Any other command, but only after you approve the exact text. |
| Stop the laptop | The backup computer takes over in about 15 seconds. |
| "wrap up", later "resume Volt" | A diary and boot state are saved and restored. |

## Quick start

**You need:** macOS, [Docker Desktop](https://www.docker.com/products/docker-desktop), [uv](https://docs.astral.sh/uv/), Node 20+, Git, [Switch Console](https://switchagents.ai) 0.40 or newer with an agent provider signed in. Linux and Windows notes are in the [setup guide](docs/SETUP.md).

```bash
git clone https://github.com/InnoShay/switchers.git
cd switchers
bash scripts/bootstrap.sh
```

`bootstrap.sh` installs the Python dependencies and a headless browser, creates `~/roomservice-workspace` with a demo project, starts a local Switch server in Docker (Switch API, Mattermost and the admin Gateway), builds the templates and runs a health check.

The rest needs a person for about ten minutes: create a registration key in the Gateway, connect Console, import two templates, pair your phone. [docs/SETUP.md](docs/SETUP.md) walks through every click. Then:

```bash
bash scripts/demo_up.sh        # Docker, Switch, health check, the desk and the Control Room
```

**Just want to see it?** The Control Room runs on its own, with no Switch, keys or Docker:

```bash
uv sync
uv run roomservice hud --demo  # http://127.0.0.1:7777, a scripted story of every event
```

## How it works

![Architecture](docs/architecture.png)

1. You speak or type in Telegram, Mattermost, or the Siri shortcut. Switch carries the message into the main chat room.
2. The **Planner** (an AI agent run by Switch Console) turns it into a task room and a plan, and asks the **Builder** and **Researcher** for work.
3. The **Computer** (this repository) executes commands on your Mac and reports every result as a message with a receipt. The **Control Room** shows each message and action live.
4. Risky steps wait for a one-time approval code that only your paired account can give.

Switch is not decoration: rooms, the agent protocol, agent-run templates, roles and leases, aliases, media upload and room commands carry the whole workflow. Without it there is no phone-to-desk link, no task rooms, no handoff and no approvals.

### The team

| Name | Type | Switch agent | Role |
|---|---|---|---|
| Planner | `@planner` | `concierge` | turns a sentence into a task room and a plan |
| Builder | `@builder` | `builder` | writes the code |
| Researcher | `@researcher` | `scout` | finds references |
| Computer | `@computer` (`@hands` works too) | `desk-laptop`, role `hands` | acts on your Mac |
| Backup computer | `@backup` | `desk-backup` | takes over when the Computer disappears |
| Assistant | `@assistant` | `life` | calendar and email through n8n (optional) |

## Safety

- The Computer obeys only the paired owner and the owner's own agents. Anyone else is refused.
- Anything outside the allowlist is refused: only the apps, pages and scripts you list in `config/desk.yaml`, plus projects you open by name. Anything else needs `exec` and your approval code.
- Risky steps (`commit`, `push`, `close all`, scripts marked `confirm`, every `exec`) wait for a code valid for five minutes, answerable only by the owner, never by voice or by an agent.
- Limits: 20 actions a minute, 5 commands per message, a loop guard on the relay, and a pause key (`S` in the Control Room) that stops everything.
- Secrets live in `.env` and `~/.roomservice` (mode 600) and are redacted from logs. The repository contains none.

Details: [docs/power.md](docs/power.md).

## Commands

```bash
uv run roomservice up              # the Computer, the Control Room, the Assistant, the scheduler
uv run roomservice backup          # the Backup computer
uv run roomservice pair            # print a pairing code for a new chat
uv run roomservice register        # register desk-laptop and life with Switch
uv run roomservice doctor          # check the whole setup, with a fix next to each problem
uv run roomservice hud --demo      # the Control Room with scripted events
uv run roomservice build-templates # rebuild switch/templates/dist/*.yaml
```

## Documentation

| Guide | What is in it |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Install from scratch, every manual step, troubleshooting table |
| [docs/try-it.md](docs/try-it.md) | Ten things to say and what you should see |
| [docs/power.md](docs/power.md) | Opening any project, approved commands, the safety model |
| [n8n/README.md](n8n/README.md) | Calendar and email (optional) |
| [SPEC.md](SPEC.md), [DECISIONS.md](DECISIONS.md) | The build specification and every decision taken against it |

## Repository

```
roomservice/        the Python package: desk (grammar, allowlist, approvals, OS adapters), agents, relay, Control Room
  hud/static/       the Control Room: plain HTML, CSS and ES modules, no build step
switch/             agent instructions and the two Switch templates (dist/ is generated and committed)
demo/volt/          the seed project the demo builds on
config/             desk.example.yaml (setup copies it to desk.yaml)
scripts/            bootstrap, Switch server setup, demo start, per-OS setup
tests/              unit, contract (against a fake Switch) and live tests
```

## Development

```bash
uv sync
uv run ruff check .
uv run pytest -m "not live"   # no network and no Switch needed
```

CI runs both on every pull request. Live tests (`-m live`) need a real Switch server and a filled `.env`.

## Credits

Built for the Flip the Switch hackathon by Yash Goel and Lakshay Sharma. #HowISwitch

Powered by [Switch](https://switchagents.ai). Released under the [MIT License](LICENSE).
