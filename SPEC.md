# RoomService — Build Specification v3.0 (FINAL)

> **"Room service. What are we building today?"**
> You say one sentence. Your room wakes up, your desk boots itself, a crew of AI agents in a Switch room takes the job, shows you proof on your phone, asks before anything risky, and closes the day with a diary that tomorrow resumes from.

| Field | Value |
|---|---|
| Product | RoomService |
| Event | Flip the Switch hackathon (WeMakeDevs × DevTools Academy × Switch AI), 4–7 Nov 2026 |
| Track | Track 02 — Best Personal or Creative Workflow ($2,000) |
| Side tracks | Code with Wispr ($500), Best Blog (AirPods 5), #HowISwitch (keyboards) |
| Hard deadline | **Sat 7 Nov 2026, 23:59 IST.** Team target: submitted by **23:15 IST** |
| Team | Lakshay Sharma, Yash Goel |
| Spec version | 3.0, written 7 Nov 2026 ~13:00 IST. Supersedes v1 and v2. |
| Verified against | docs.switchagents.ai and github.com/sandbox-quantum/switch `main`, read 7 Nov 2026 |

---

## 0. READ THIS FIRST — instructions for Claude Code

You are a fresh Claude Code session. This file is your **only** context. It contains the goal, every design decision, every interface, every prompt, every test, and the work split between the two humans. Follow it literally.

### 0.1 Operating procedure (every session)
1. Identify the operator: **Lakshay** or **Yash**. If the user's first message doesn't say, ask exactly once: "Am I working as Lakshay or Yash?"
2. Run `git fetch --all && git checkout main && git pull`.
3. Run `bash scripts/tickets.sh` (created in RS-01; before RS-01 exists, treat all tickets as open). It prints which tickets are merged, based on merged PR titles (§25).
4. Pick the operator's lowest-numbered open ticket whose dependencies are all merged (§24). Tell the operator which ticket you're starting, in one line.
5. Create the branch exactly as §25.2 says. Implement **only** that ticket's scope and files (§24 cards, §7.2 ownership).
6. Meet the ticket's acceptance criteria. Run `uv run ruff check . && uv run pytest -m "not live"` — must be green.
7. Open the PR with the exact title and body format of §25.3 using `gh pr create`.
8. Report to the operator: PR link, what's done, what they must do by hand (if anything), the next ticket.

### 0.2 Rules
- **Never invent** names, ports, paths, message formats, prompts or file locations. They are all here. If something is genuinely missing, choose the simplest option, write one line in `DECISIONS.md` (`RS-XX: decision — reason`), and continue.
- **Never edit another ticket's files** (§7.2). Contracts in `roomservice/contracts/` change only through an `RS-00:` PR that both humans approve.
- **Never commit secrets.** `.env`, `~/.roomservice/*` are never in git. Logs redact keys.
- **Never call real Switch in unit/contract tests.** Use `tests/contract/fake_switch.py`. Live tests are marked `@pytest.mark.live`.
- Items marked **[SPIKE Sx]** depend on Switch behaviour not fully verifiable from docs. Implement the primary path **and** the stated fallback behind a config flag; the spike result picks the default.
- MUST = required for the demo. SHOULD = do if on schedule. MAY = only if everything else is done.
- Keep the operator informed with one-line updates between big steps; no long narration.

---

## 1. The hackathon (what we must satisfy)

### 1.1 Brief
"Take an AI agent you already use (Claude Code, Codex, Cursor, OpenCode, Antigravity), connect it to Slack, Teams, Discord, Telegram or Mattermost with **Switch**, and build a workflow where it gets real work done with people." Minimum: **at least one AI agent and one person get a real task done together in team chat, connected through Switch.** Switch must be central; the README must show how it's used.

### 1.2 Judging (weights read from the event page source)
| Criterion | Weight | Judge's question | How RoomService wins it |
|---|---|---|---|
| Use of Switch | **30%** | Is Switch central; would the project stop working without it? | 13 Switch primitives carry the workflow (§3.5). No Switch → no phone↔desk link, no mission rooms, no role handoff, no approvals. |
| Technical execution | **25%** | Does it run; can someone clone and reproduce it? | Templates, `roomservice doctor`, `--dry-run`, fake Switch for CI, seed project, tests. |
| Creativity & impact | **25%** | Fresh idea solving a real problem? | The room gets a body; nobody else in the field does this (§3.4). |
| Presentation | **20%** | Do demo video and README make Switch usage clear? | Split-screen video phone+desk, HUD, README opens with "What breaks without Switch". |

Pipeline: WeMakeDevs reviews all → WeMakeDevs shortlists → Switch + DevTools Academy + WeMakeDevs judge finalists. **The first 15 seconds of the video and the first screen of the README decide the shortlist.**

### 1.3 Deliverables
Public repo, demo video, README. Code with Wispr also needs each builder's **Wispr Flow Insights screenshot**. Submit at `https://www.wemakedevs.org/hackathons/switch/submit`.

### 1.4 Rules that bite
Switch setup and the agents' workflow must be built during the event (4–7 Nov). AI coding tools allowed; we must understand and be able to explain the code. Entrants 18+, real identities. Repo must contain no third-party confidential data or malicious code. Team ≤ 4 (we are 2).

### 1.5 The field (what we must beat)
Published Flip the Switch entries are mostly **"N specialist agents debate in a room while a human approves"**: Investor Council (bull/bear), IDEAForge (4 agents argue about inventions), LabRoom (7 Claude Code agents as lab scribe/auditor; excellent polish), ShipRoom (release readiness), Refund Court (courtroom). Outside the hackathon, OpenClaw is the 2026 reference personal agent (one assistant via Telegram/WhatsApp), and many "Jarvis" repos do voice + app opening for one user with no persistence or sharing. Nate Herk's popular n8n "Personal Assistant" (Telegram trigger → transcription → one AI agent with email/calendar/contacts/research sub-agents + memory → text/voice reply) is one private bot with no shared room and no computer control.
**Our gap:** nobody gives the room a *body* (an agent that physically acts on your machine through Switch), nobody spawns rooms per mission, nobody moves a role between machines, nobody has a cinematic live view.

---

## 2. Team

| Person | Strengths assumed | Owns |
|---|---|---|
| **Lakshay Sharma** | Python, systems | The RoomService runtime: Switch client, desk (hands), relay, roles/handoff, CLI, hardening, demo recording |
| **Yash Goel** | Has Switch Console + server running already | Switch server/Console, agents, templates, prompts, Telegram, n8n life agent, HUD, seed project, README/blog |

Each builder runs their own Claude Code session with this spec. Work is split into tickets RS-01…RS-16 (§24), merged via PRs whose titles carry the ticket ID (§25).

---

## 3. Product

### 3.1 Pitch
RoomService turns your physical room into a Switch room: one spoken sentence boots your desk, spawns a mission room with a crew of agents, and keeps you in control from your phone — with a computer that acts only through Switch.

### 3.2 Problem (personal, everyday)
Every work or creative session starts with 20–40 minutes of friction: open the right folder, apps, tabs, music; remember where you stopped; check the calendar; tell people what you're doing. AI helpers live in separate tabs, forget everything, and can't safely touch your machine.

### 3.3 Golden path (what the user experiences)
1. Phone, Wispr Flow active, Telegram group **RoomService HQ**: *"Room service. Tonight we ship the Volt waitlist page. Block nine to eleven and remind me at eleven."*
2. **≤ 3 s:** the laptop says "Evening. Booting Volt." The Mission Control HUD ignites full screen (light on via webhook, or the HUD's light-flash), VS Code opens the project, a terminal starts the dev server, the browser opens localhost, focus mode turns on, music starts.
3. **≤ 75 s:** `@concierge` posts a mission card in HQ; a new Mattermost channel `mission-volt-waitlist` appears with the crew and the brief; `@life` confirms the calendar block.
4. `@builder` builds. Permission requests are mirrored to the phone; the owner replies `ok K7Q3`.
5. "Show me" → a screenshot of the running page arrives on the phone. "Make the button orange and bigger" → new screenshot ≤ 2 min later.
6. Laptop lid closes (or runtime killed). `desk-backup` on the second machine takes the `hands` role. HUD there: **HANDS TRANSFERRED**.
7. "Wrap up" → diary + boot state saved in the room, commit after approval, spoken goodnight, apps close. Tomorrow: "Room service, resume Volt" restores everything.

### 3.4 Differentiators (say these in the video and README)
1. **The room has a body.** `hands` is a program agent on the real machine, joined through Switch's agent protocol — not a chatbot.
2. **Ignition in 3 seconds.** Physical response before any LLM has finished thinking.
3. **Missions build their own rooms** via Switch's agent-run templates: same shape every time, linked to HQ.
4. **Hands is a role that migrates** between machines; the room survives a closed laptop.
5. **Phone-to-desk relay with owner-only approval codes**: autonomy with a leash.
6. **Mission Control HUD**: a live cinematic view of the room.
7. **n8n becomes a teammate** (`@life`) instead of a private bot.
8. **Built by voice** end to end with Wispr Flow, and voice is the product's front door.

### 3.5 Why Switch is load-bearing
| Switch primitive | Used for | Spec § |
|---|---|---|
| Rooms bridged to Telegram + Mattermost | HQ on phone, missions on desk | 9 |
| Agent protocol (WebSocket + HTTP) | Our own `desk-*` and `life` agents | 11 |
| Agent-run templates (`run_template`) | Mission rooms spawned deterministically | 10.4 |
| Room instructions | Every agent briefed once | 10 |
| Room documents | Mission brief, day diary, boot state | 10, 12.8 |
| Roles + leases | `hands` role moving between machines | 15 |
| Room links | HQ ↔ mission signposts | 10.5 |
| Aliases | `@hands` usable in HQ rooms too | 9.4 |
| Addressing rules | Desk obeys only owner + owner's agents | 17 |
| In-room approvals ("yes") | Builder's risky steps | 13.3 |
| Media upload | Screenshots from desk into rooms | 11.2 |
| Typing indicator | "Hands is typing…" during actions | 11.7 |
| Room commands | `!assign-agent`, `!set-alias`, `!roles` | 9.4 |

---

## 4. Switch primer (what a fresh session must know)

- **Switch** is open-source infrastructure that puts AI agents into team chat. It ships no agents/models. A **server** (Docker; bundles Mattermost) + **Switch Console** (desktop app) that runs coding agents (Claude Code, Codex, OpenCode…) and connects chat apps.
- **Room** = a chat channel + shared log + instructions, documents, references, roles. Agents and people are members. Messages are an append-only log per room.
- **Addressing:** an agent acts on a message only when it is `@mentioned` (or follow-ups / a main agent apply). Mentioning the name of a **role** reaches whoever holds the role. **Aliases** give an agent a short room-specific name.
- **Who can instruct an agent** (addressing setting): owner only (default), owner and owner's agents, anyone. Switch refuses others before the agent acts.
- **Session:** the running copy of an agent. Console runs sessions for Console agents. Our own agents connect through the **agent protocol**: register once (`POST /agents` with a registration key → `{id, api_key}`), open a WebSocket per room, answer pings every 2 s, act only on `message` events with `payload.addressed == true`, call operations at `POST /agents/{id}/ops/{name}`.
- **Operations** relevant to us: `list_rooms`, `list_all_rooms`, `get_room_detail`, `connect_to_room`, `create_room`, `update_room`, `archive_room`, `list_participants`, `invite_agent_to_room`, `post_message`, `send_targeted_message`, `read_context`, `create_room_document`, `update_room_document`, `load_internal_documents`, `list_roles`, `define_role`, `assume_role`, `release_role`, `link_rooms`, `list_linked_rooms`, `list_templates`, `get_template`, `run_template`, `create_room_from_yaml`, `save_template`, `update_agent_detail`. Console-run Claude Code agents get these as Switch tools automatically.
- **Templates:** YAML documents that create rooms (and agents). `run_template` lets an agent create a room from a saved template; the template's `kickoff:` message wakes mentioned agents.
- **Approvals:** with Auto mode on, a Console agent posts a permission request in the room; a reply of exactly `yes` or `no` (from someone it takes messages from) answers it.
- **Known limits:** no timers (agents can't wake themselves); a busy agent may drop a new message; Telegram bots can't create groups; an agent holds **one role at a time across all rooms**; instruction edits need an agent restart; @mentions inside pinned docs wake agents; dates may arrive in UTC; quitting Console stops Console-run agents; a Console-run local server "isn't an address you hand out" to other machines.
Full verified API detail: **Appendix A**.

---

## 5. Architecture

### 5.1 Components
| ID | Component | Tech | Runs on | Ticket(s) |
|---|---|---|---|---|
| C1 | Switch server + Mattermost | Switch Console local server (Docker) | Demo machine | RS-02 |
| C2 | Telegram bridge | Switch Telegram connection (one BotFather bot) | Switch server | RS-09 |
| C3 | `concierge` | Claude Code via Console | Demo machine | RS-04 |
| C4 | `builder` | Claude Code via Console | Demo machine | RS-04 |
| C5 | `scout` (SHOULD) | Claude Code via Console | Demo machine | RS-04 |
| C6 | RoomService runtime `roomservice up` | Python 3.12 package | Demo machine | RS-03/05/07/10/12 |
| C6a | `desk-laptop` agent (hands) | runtime | Demo machine | RS-07 |
| C6b | `life` agent bridge | runtime | Demo machine | RS-11 |
| C6c | Relay | runtime | Demo machine | RS-10 |
| C6d | Scheduler | runtime | Demo machine | RS-11 |
| C6e | HUD server | FastAPI in runtime, port 7777 | Demo machine | RS-08 |
| C7 | HUD frontend | static HTML/CSS/JS | Browser on demo machine | RS-08 |
| C8 | n8n + `RoomService Life` workflow | Docker `n8nio/n8n`, port 5678 | Demo machine | RS-11 |
| C9 | `desk-backup` (SHOULD) | runtime `roomservice backup` | Second machine | RS-12 |
| C10 | Seed project `volt` | Vite + TS | Demo machine | RS-06 |

### 5.2 Machine topology (decided)
- **Demo machine** = the machine where Switch server, Console, all Console agents, n8n, the runtime (`desk-laptop`) and the HUD run, and where the dev server and VS Code open. **Rule: if either teammate has a Mac, the demo machine is a Mac (Yash's if he has one, else Lakshay's). Otherwise Yash's machine.** Builder, dev server and desk must be on the same machine because the builder edits files the desk opens.
- **Second machine** = the other teammate's laptop. Runs only `roomservice backup` (`desk-backup`) for the handoff (SHOULD).
- **Reaching the server from the second machine** [SPIKE S0]: try `SWITCH_URL=http://<demo-machine-LAN-IP>:<port>`. Fallback (always works): SSH port forward from the second machine: `ssh -N -L <port>:127.0.0.1:<port> <user>@<demo-machine-LAN-IP>` then `SWITCH_URL=http://127.0.0.1:<port>`. (macOS: System Settings → General → Sharing → Remote Login on. Windows: enable OpenSSH Server.)
- **During development** each builder runs their own Console local server for live tests; contract tests need no server.

### 5.3 Data flow (golden path)
```
Phone (Telegram + Wispr) ─▶ Switch Telegram bridge ─▶ HQ room "RoomService HQ"
                                                         │ every message (filter=all)
              ┌──────────────────────────────────────────┤
              ▼                                          ▼
     desk-laptop (runtime)                       concierge (Claude Code, main agent of HQ)
  owner wake phrase → IGNITION                 plan → run_template(roomservice-mission)
  boot profile · speak · HUD · lights          → link_rooms · post plan · mission card in HQ
              │                                          │
              │        mission-<slug> (Mattermost) ◀─────┘ kickoff: "@desk-laptop mission <slug> <project>"
              │                 │                                   "@builder …"
              ├─ assume_role(hands)                                 
              ├─ receipts / media ─▶ mission room ◀── builder: "@hands shot page"
              ├─ relay mirror ─────────────────────▶ HQ (plan, shots, approvals, done)
              └─ HUD bus ─▶ http://127.0.0.1:7777 (Mission Control)
                                mission room ◀── life (runtime) ⇄ n8n webhook ⇄ Google Calendar/Gmail
```

### 5.4 Key sequences
**Ignition + mission spawn**
1. Owner message in HQ contains a wake phrase → desk (non-addressed exception) matches the paired owner id → HUD `ignition`, lights, speak, `boot <project>`, post `⚡ ignition · booting volt` in that HQ room.
2. Same message reaches concierge (main agent) → `list_templates` → `run_template` → room `mission-volt-waitlist` created; kickoff posted as concierge: `@desk-laptop mission volt-waitlist volt` and `@builder …`.
3. Desk RoomWatcher sees the new room (≤ 3 s), opens a WebSocket, receives the kickoff (addressed), executes `mission`: release role elsewhere, `assume_role(hands)`, skip boot (already booted), receipt, HUD `mission`.
4. Concierge `link_rooms` both ways, posts plan in mission room (ends with `@builder go.`), posts mission card in HQ, posts `@life …` in HQ if there were everyday asks.
5. Relay mirrors the plan's first 6 lines into HQ.

**Proof loop**
Owner: "show me" → concierge posts `@hands shot page` in the mission room → desk captures, uploads PNG to mission room → relay re-uploads to every HQ room.

**Approval loop (desk)**
`@hands commit "…"` → desk posts `⚠️ approval needed … ok K7Q3` in mission room → relay mirrors to HQ → owner replies `ok K7Q3` in HQ (non-addressed; desk reads it) → desk verifies paired owner → executes → `✅ approved by …`.

**Handoff**
Laptop runtime stops renewing its lease → lease lapses → backup's 5-s `assume_role` poll succeeds → backup posts `🫱 hands is now on desk-backup` → future `@hands` messages go to backup.

---

## 6. Tech stack (final)
| Area | Choice |
|---|---|
| Runtime | Python **3.12**, **uv** |
| WebSocket client | `websockets>=14`, import `from websockets.asyncio.client import connect`; headers via **`additional_headers=`** (not `extra_headers`) |
| HTTP | `httpx>=0.27` (AsyncClient) |
| Models | `pydantic>=2.7` |
| Config | `pyyaml`, `python-dotenv` |
| CLI | `typer`, `rich` |
| Screenshots | `mss` + `Pillow` (screen); `playwright` chromium (page, SHOULD) |
| HUD server | `fastapi`, `uvicorn[standard]` |
| Scheduler | `apscheduler>=3.10,<4` (AsyncIOScheduler) |
| Tests | `pytest`, `pytest-asyncio` (mode=auto), `respx`, `freezegun` |
| Lint | `ruff` (line length 100) |
| HUD frontend | Plain HTML + CSS + ES modules, Canvas 2D, Web Audio; fonts Space Grotesk + JetBrains Mono (Google Fonts). No build step. |
| n8n | `docker.n8n.io/n8nio/n8n:latest`, Docker Compose |
| n8n LLM | Anthropic Chat Model (Claude Sonnet) if `ANTHROPIC_API_KEY` exists in n8n credentials, else OpenAI Chat Model |
| Seed project | Node **20+**, Vite 5, TypeScript, no framework |
| OS | macOS primary; Windows + Linux adapters implemented and unit-tested |
| CI | GitHub Actions: ruff + pytest (not live) on PRs; PR-title check |

---

## 7. Repository

### 7.1 Layout (exact)
```
roomservice/                         (repo root — already exists; RS-01 adds files, never deletes existing ones)
├── SPEC.md  README.md  DECISIONS.md  VOICE_LOG.md  LICENSE(MIT)  .env.example  .gitignore
├── pyproject.toml
├── .github/
│   ├── workflows/ci.yml             # §25.6
│   ├── workflows/pr-title.yml       # §25.6
│   ├── pull_request_template.md     # §25.3
│   └── CODEOWNERS                   # §25.7
├── roomservice/
│   ├── __init__.py                  # __version__ = "1.0.0"
│   ├── contracts/                   # FROZEN in RS-01 (§8)
│   │   ├── __init__.py
│   │   ├── config.py                # Settings (.env) + DeskConfig (desk.yaml) pydantic models
│   │   ├── events.py                # HUD event models
│   │   ├── switch.py                # Frame/event models + SwitchHTTP Protocol
│   │   ├── agent.py                 # ProtocolAgent ABC, RoomInfo, RoomKind
│   │   └── os.py                    # OSAdapter Protocol, RunResult
│   ├── cli.py                       # typer app (§11.9)
│   ├── log.py  store.py  bus.py     # logging, ~/.roomservice persistence, HUD pub/sub
│   ├── switch/http.py  switch/connection.py  switch/rooms.py
│   ├── agents/base.py  agents/desk.py  agents/life.py  agents/backup.py
│   ├── desk/grammar.py  desk/allowlist.py  desk/approvals.py  desk/ignition.py
│   ├── desk/state.py  desk/actions.py  desk/receipts.py
│   ├── desk/os/macos.py  desk/os/windows.py  desk/os/linux.py  desk/os/dry.py  desk/os/__init__.py
│   ├── relay.py  scheduler.py  voice.py  doctor.py  spikes.py  templates_build.py
│   └── hud/server.py  hud/demo.py  hud/static/{index.html,hud.css,hud.js,orb.js,sfx.js}
├── config/desk.example.yaml
├── switch/
│   ├── instructions/{hq-room.md,concierge.md,builder.md,scout.md,mission-room.md}
│   └── templates/{roomservice-crew.template.yaml,roomservice-mission.template.yaml}
│       └── dist/                    # generated by `roomservice build-templates` (committed)
├── n8n/{life.workflow.json,README.md}
├── infra/docker-compose.n8n.yml
├── demo/volt/                       # seed project
├── demo/script.md
├── docs/{architecture.png,wispr/}
├── scripts/{tickets.sh,setup_mac.sh,setup_windows.ps1}
└── tests/
    ├── conftest.py
    ├── unit/
    ├── contract/fake_switch.py  contract/test_*.py
    ├── fixtures/
    └── live/
```

### 7.2 File ownership (prevents merge conflicts)
| Path | Owner | Created by |
|---|---|---|
| `pyproject.toml`, `.github/*`, `roomservice/contracts/*`, `log.py`, `store.py`, `bus.py`, `scripts/tickets.sh`, `tests/conftest.py` | Lakshay | RS-01 (later dependency additions: the ticket that needs them adds them in its own PR, one line each) |
| `roomservice/switch/*`, `agents/base.py`, `spikes.py` | Lakshay | RS-03 |
| `roomservice/desk/*` (except `os/`), `voice.py` | Lakshay | RS-05/RS-07 |
| `roomservice/desk/os/*`, `agents/desk.py`, `cli.py`, `doctor.py` | Lakshay | RS-07 (Yash's tickets add CLI subcommands by adding a function in their own module and one `app.command()` line in `cli.py` — allowed) |
| `relay.py` | Lakshay | RS-10 |
| `agents/backup.py` | Lakshay | RS-12 |
| `switch/*`, `templates_build.py` | Yash | RS-04 |
| `config/desk.example.yaml`, `demo/volt/*`, `scripts/setup_*` | Yash | RS-06 |
| `roomservice/hud/*` | Yash | RS-08 |
| `n8n/*`, `infra/*`, `agents/life.py`, `scheduler.py` | Yash | RS-11 |
| `README.md`, `docs/*`, `VOICE_LOG.md`, `demo/script.md` | Yash | RS-15 |
| `SPEC.md`, `DECISIONS.md` | Both | via `RS-00:` PRs only |

---

## 8. Frozen contracts (RS-01 implements these exactly; everything else codes against them)

### 8.1 `contracts/config.py`
```python
class Settings(BaseSettings):          # from .env (pydantic-settings) — add pydantic-settings dep
    switch_url: AnyHttpUrl
    switch_registration_key: SecretStr | None = None
    roomservice_agent: Literal["desk-laptop", "desk-backup"] = "desk-laptop"
    roomservice_hq_rooms: list[str] = ["roomservice-hq", "RoomService HQ"]   # names or room UUIDs, comma-separated in .env
    roomservice_tz: str = "Asia/Kolkata"
    roomservice_home: Path = Path("~/.roomservice").expanduser()
    roomservice_desk_config: Path = Path("config/desk.yaml")
    roomservice_dry_run: bool = False
    roomservice_handoff_mode: Literal["lease", "explicit"] = "lease"         # S8 picks default
    roomservice_relay_approvals: bool = True                                  # S5 picks default
    hud_port: int = 7777
    n8n_life_url: AnyHttpUrl = "http://localhost:5678/webhook/roomservice-life"
    n8n_life_token: SecretStr = SecretStr("change-me")
    lights_on_url: str | None = None
    lights_off_url: str | None = None

class AppTarget(BaseModel): mac: str; win: str; linux: str
class ScriptDef(BaseModel): cmd: list[str]; cwd: Literal["project", "home"] = "project"; confirm: bool = False; timeout_s: int = 120
class Terminal(BaseModel): name: str; cmd: str
class Project(BaseModel):
    keywords: list[str]; path: Path; open_editor: bool = True
    terminals: list[Terminal] = []; urls: list[str] = []          # each url: alias key or http(s) URL
    wait_for: str | None = None; screenshot_url: str | None = None
    focus: bool = True; music: str | None = None; lights: bool = True
class Profile(BaseModel): apps: list[str] = []; urls: list[str] = []; focus: bool = True; lights: bool = True; music: str | None = None
class Voice(BaseModel): enabled: bool = True; voice_name: str = "Samantha"; rate: int = 190
class Ignition(BaseModel): wake_phrases: list[str]; default_profile: str
class Schedule(BaseModel): morning_brief: str = "08:55"; morning_days: str = "mon-sat"; wrap_nudge: str = "23:00"
class Limits(BaseModel): actions_per_minute: int = 20; max_commands_per_message: int = 5; approval_ttl_s: int = 300
class DeskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]; machine_name: str; timezone: str
    voice: Voice; ignition: Ignition
    apps: dict[str, AppTarget]; urls: dict[str, HttpUrl]; scripts: dict[str, ScriptDef]
    projects: dict[str, Project]; profiles: dict[str, Profile]
    schedule: Schedule = Schedule(); limits: Limits = Limits()
def load_settings() -> Settings: ...
def load_desk_config(path: Path) -> DeskConfig: ...   # expands ~, raises ConfigError("<yaml.path>: <msg>")
```

### 8.2 `contracts/events.py` (HUD events; JSON over `ws://127.0.0.1:7777/ws`)
All events: `type: str`, `ts: int` (epoch ms). Pydantic models with a discriminated union `HudEvent`.
| type | fields |
|---|---|
| `hello` | `mission: str|None`, `crew: list[{name, color, state}]`, `connections: {switch: bool, n8n: bool}`, `machine: str` |
| `ignition` | `project: str`, `lights: Literal["webhook","flash"]` |
| `mission` | `slug`, `title: str|None`, `started_at: int` |
| `message` | `room`, `room_kind: Literal["hq","mission","other"]`, `sender_name`, `agent: str` (crew key or `"you"` or `"other"`), `body` (≤ 400 chars), `addressed: bool` |
| `agent_state` | `agent`, `state: Literal["offline","idle","working","needs_you"]` |
| `action_start` | `id`, `verb`, `args: list[str]`, `room` |
| `action_end` | `id`, `ok: bool`, `ms: int`, `summary: str` |
| `approval_open` | `code`, `cmd`, `expires_at: int` |
| `approval_closed` | `code`, `result: Literal["ok","no","expired"]`, `by: str|None` |
| `screenshot` | `url` (e.g. `/shots/shot-volt-143201.png`), `caption` |
| `speak` | `text` |
| `transfer` | `from_agent`, `to_agent` |
| `freeze` | `on: bool` |
| `system` | `level: Literal["info","warn","error"]`, `text` |

Crew keys and colours: `you #F5F7FA`, `concierge #7C9CFF`, `builder #FFB547`, `scout #4FD1C5`, `hands #FF5C7A`, `life #9BE564`.
`bus.py`:
```python
class Bus:
    def publish(self, ev: HudEvent) -> None            # fan-out; per-subscriber queue 500, drop oldest on overflow
    async def subscribe(self) -> AsyncIterator[HudEvent]
    def snapshot(self) -> HelloEvent                    # kept current from published events: mission, crew states, connections, machine
    on_freeze: Callable[[bool], Awaitable[None]] | None = None   # set by DeskAgent at start; HUD /api/freeze calls it
bus = Bus()                                             # module-level singleton shared by runtime and HUD server (same process)
```

### 8.3 `contracts/switch.py`
```python
class DomainEvent(BaseModel):          # data of {"event": ..., "data": {...}, "id": n}
    type: Literal["message","command","room_join"]
    room_id: str; bridge_id: str | None = None; channel_type: str | None = None
    payload: dict; sequence: int
class MessagePayload(BaseModel):
    addressed: bool; sender: str; sender_name: str; message_id: str; body: str
    timestamp: int; thread_id: str | None = None; attachments: list[dict] = []
class OpError(Exception): status: int; detail: str
class SwitchHTTP(Protocol):
    async def health(self) -> bool
    async def register(self, name: str, display_name: str, description: str, connector_type: str, overwrite: bool = False) -> tuple[str, str]   # (id, api_key)
    async def list_ops(self) -> dict
    async def op(self, name: str, args: dict, conn_id: str | None = None) -> Any          # drops None values from args
    async def post(self, room_id: str, content: str) -> str                                 # event_id
    async def upload(self, room_id: str, files: list[tuple[str, bytes, str]], caption: str | None = None, thread_id: str | None = None) -> dict
    async def typing(self, room_id: str, on: bool) -> None                                  # never raises
    async def renew_lease(self, conn_id: str) -> bool
```

### 8.4 `contracts/agent.py`
```python
class RoomKind(StrEnum): HQ="hq"; MISSION="mission"; OTHER="other"
class RoomInfo(BaseModel): id: str; name: str; kind: RoomKind; conn_id: str | None = None
class ProtocolAgent(ABC):
    name: str
    async def start(self) -> None          # registration loaded, watcher started
    async def stop(self) -> None
    @abstractmethod
    async def on_message(self, room: RoomInfo, ev: DomainEvent, msg: MessagePayload) -> None
    async def reply(self, room: RoomInfo, text: str, thread_id: str | None = None) -> None
    async def upload(self, room: RoomInfo, png: bytes, filename: str, caption: str, thread_id: str | None = None) -> None
    def hq_rooms(self) -> list[RoomInfo]
```

### 8.5 `contracts/os.py`
```python
class RunResult(BaseModel): code: int; stdout_tail: str; stderr_tail: str; ms: int     # tails = last 15 lines
class OSAdapter(Protocol):
    name: Literal["macos","windows","linux","dry"]
    async def open_app(self, target: str) -> None
    async def quit_app(self, target: str) -> None
    async def open_url(self, url: str) -> None
    async def open_in_editor(self, path: Path) -> None
    async def open_terminal(self, cwd: Path, cmd: str, title: str) -> None
    async def run(self, argv: list[str], cwd: Path, timeout_s: int) -> RunResult
    async def focus(self, on: bool) -> bool                    # False = unsupported
    async def screenshot_screen(self) -> bytes                 # PNG, primary monitor
    async def speak(self, text: str, voice: str, rate: int) -> None
def get_adapter(dry_run: bool) -> OSAdapter: ...               # by platform.system()
```

---

## 9. Switch setup (human steps; Yash owns)

### 9.1 Install (RS-02)
1. Docker Desktop running.
2. Switch Console latest stable (hackathon Resources page). Add server → "Let Switch Console run a server". Home must show **Running** and Mattermost.
3. Agent providers: Claude Code installed and signed in (`claude auth login`).
4. Console Home → copy **Server address** → `.env` `SWITCH_URL`. Check `curl -s -o /dev/null -w "%{http_code}" $SWITCH_URL/health` → `200`.
5. Gateway → **API Keys** → create a key of type **registration** → `.env` `SWITCH_REGISTRATION_KEY`.
6. Mattermost: sign in (Console Home → Mattermost → Sign-in details); install the Mattermost desktop app; note your Mattermost **username**.
7. Optional for devs: connect the docs MCP to Claude Code: `claude mcp add switch-docs --transport http https://docs.switchagents.ai/mcp`.

### 9.2 Order of creation (matters)
1. Register runtime agents first (`uv run roomservice register` → `desk-laptop`, `life`), because templates name them and Switch refuses templates naming missing agents.
2. Build + import crew template (creates `concierge`, `builder`, `scout` and room `roomservice-hq` containing all five agents + owner).
3. Save mission template as shared `roomservice-mission`.
4. Telegram HQ.
5. Pair the owner.

### 9.3 Console agent settings (after crew template)
For `concierge`, `builder`, `scout`: **Who can talk to your agent → Me and my agents**; Auto mode **on**; Bypass permissions **off**; check Provider sign-in ✅.

### 9.4 Telegram HQ (RS-09)
1. `@BotFather` → `/newbot` → name `RoomService`, username `<something>_roomservice_bot`. Save the token in a password manager.
2. BotFather `/mybots` → bot → Bot Settings → **Group Privacy → Turn off** *before* adding the bot anywhere.
3. Console → server Home → Messaging apps → Connect → Telegram → token + bot username → Connect.
4. Telegram (account must have an `@username`): create group **RoomService HQ**, add the bot. Switch creates a room. Link your Telegram account when Console Home prompts.
5. In the Telegram group send, one per message:
   `!invite-agent @concierge` · `!invite-agent @desk-laptop` · `!invite-agent @life` · `!assign-agent @concierge` · `!set-alias @desk-laptop @hands`
6. In Mattermost `roomservice-hq` send: `!assign-agent @concierge` · `!set-alias @desk-laptop @hands`.
7. Set Telegram HQ room instructions = `switch/instructions/hq-room.md` (Console → room → Configuration → Instructions). (Mattermost HQ gets them from the crew template.)
8. Run `uv run roomservice doctor` → it lists every room the desk sees; confirm both HQ names match `ROOMSERVICE_HQ_ROOMS` (use room UUIDs there if names differ).

### 9.5 Pairing (RS-07 implements; owner does once per surface)
`uv run roomservice pair` prints a 6-digit code valid 10 min and waits. From **each** surface (Mattermost and Telegram) post in an HQ room: `@hands pair 482913`. Desk stores `{sender, sender_name, room_name}` in `~/.roomservice/owners.json`, replies `🔐 paired · <sender_name> on <room name>`. Only paired sender ids can: trigger ignition, approve (`ok/no`), `freeze/unfreeze`, `pair` again. Agents can never pair (reject if sender is any agent in `list_participants`).

---

## 10. Switch-side content (Yash owns, RS-04)

### 10.1 Agent roster
| Name | Display | Runs as | Directory (demo machine) | Addressing | Model |
|---|---|---|---|---|---|
| `concierge` | Concierge | Claude Code (Console) | `~/roomservice-workspace/concierge` | owner_and_owner_agents | provider default |
| `builder` | Builder | Claude Code (Console) | `~/roomservice-workspace` | owner_and_owner_agents | provider default |
| `scout` | Scout | Claude Code (Console) | `~/roomservice-workspace/scout` | owner_and_owner_agents | provider default |
| `desk-laptop` | Hands · laptop | runtime | — | owner_and_owner_agents | none |
| `desk-backup` | Hands · backup | runtime (2nd machine) | — | owner_and_owner_agents | none |
| `life` | Life | runtime → n8n | — | owner_and_owner_agents | n8n |
Projects: `~/roomservice-workspace/projects/<key>`; seed = `projects/volt`.

### 10.2 `templates_build.py` (`uv run roomservice build-templates`)
Reads each `switch/templates/*.template.yaml`, replaces every scalar string exactly equal to `"@@FILE:<name>.md@@"` with the contents of `switch/instructions/<name>.md`, dumps with `yaml.safe_dump(sort_keys=False, allow_unicode=True, width=10_000)` forcing literal block style (`|`) for multi-line strings (custom representer), writes `switch/templates/dist/<same name>`. Fails if any `@@FILE:` remains or a file is missing. Idempotent. Unit test: round-trip preserves newlines.

### 10.3 Crew template (`switch/templates/roomservice-crew.template.yaml`)
```yaml
version: 1
params:
  workspace: {type: directory, label: Workspace folder, default: "~/roomservice-workspace"}
  provider:  {type: provider, default: [claude], input: advanced}
  location:  {type: location, default: local, input: advanced}
  bridge:    {type: bridge, default: [Mattermost, $first], input: advanced}
agents:
  - name: concierge
    display_name: Concierge
    description: Turns one spoken sentence into a mission room, a crew and a plan.
    provider: "{provider}"
    location: "{location}"
    directory: "{workspace}/concierge"
    addressing: owner-agents
    auto_mode: true
    instructions: "@@FILE:concierge.md@@"
  - name: builder
    display_name: Builder
    description: Builds the mission's project and asks hands for proof.
    provider: "{provider}"
    location: "{location}"
    directory: "{workspace}"
    addressing: owner-agents
    auto_mode: true
    instructions: "@@FILE:builder.md@@"
  - name: scout
    display_name: Scout
    description: Finds references and registers them in the mission room.
    provider: "{provider}"
    location: "{location}"
    directory: "{workspace}/scout"
    addressing: owner-agents
    auto_mode: true
    instructions: "@@FILE:scout.md@@"
room:
  name: roomservice-hq
  description: RoomService headquarters. Speak a mission here.
  bridge: "{bridge}"
  channel_type: channel_public
  instructions: "@@FILE:hq-room.md@@"
  agents: [concierge, builder, scout, desk-laptop, life]
  users: ["{$creator}"]
kickoff: "@concierge introduce the crew in three short lines and say you're ready for a mission."
```

### 10.4 Mission template (`switch/templates/roomservice-mission.template.yaml`)
```yaml
version: 1
params:
  slug:    {type: string, label: Mission slug, pattern: "^[a-z0-9][a-z0-9-]{2,38}$"}
  title:   {type: string, label: Mission title}
  brief:   {type: string, label: Spoken brief verbatim, multiline: true}
  project: {type: string, label: Project key from desk.yaml or none, default: none}
  bridge:  {type: bridge, default: [Mattermost, $first], input: advanced}
room:
  name: "mission-{slug}"
  description: "RoomService mission: {title}"
  bridge: "{bridge}"
  channel_type: channel_public
  instructions: "@@FILE:mission-room.md@@"
  agents: [concierge, builder, scout, desk-laptop, life]
  users: ["{$creator}"]
  roles:
    - name: hands
      exclusive: true
      instructions: "The body of the room: a program that executes the hands grammar on a real computer. Address @hands with one command per line."
  docs:
    - name: mission-brief
      description: The mission as spoken, its slug and project.
      instructions: Read first. Do not edit.
      content: |
        # {title}

        **Spoken brief:** {brief}

        **Mission slug:** {slug}
        **Project key:** {project}
kickoff: |
  @desk-laptop mission {slug} {project}
  @builder the brief is in this room's documents. Wait for the concierge's plan, then start.
```
Why `@desk-laptop` (not `@hands`) in the kickoff: at kickoff nobody holds `hands` yet; the desk assumes it while executing `mission`. **[SPIKE S4]** verifies agent-run template + kickoff. Fallback: concierge calls `create_room` with the same name, instructions, agents, roles (`[{"name":"hands","exclusive":true,"instructions":"…"}]`), then `create_room_document(mission-brief)`, then `post_message` with the kickoff text (concierge.md contains both paths; flag in concierge.md "Template path: ON").

### 10.5 `switch/instructions/hq-room.md`
```markdown
# RoomService HQ

The owner's control room. The owner speaks through Wispr Flow, so expect spoken,
unpunctuated sentences and small transcription errors ("room service" may appear as
"roomservice" or "room servis").

Time zone: Asia/Kolkata (IST). Timestamps may arrive in UTC; always convert to IST.

Crew:
- concierge: main agent here. Turns a sentence into a mission and talks to people.
- hands (desk-laptop, alias @hands here): a PROGRAM, not a model. It understands only
  the hands grammar, one command per line.
- life: calendar and email through n8n. Creates events and drafts. Never sends email.
- builder, scout: work inside mission rooms.

Rules for every agent:
- Never narrate plumbing (sessions, connections, tools, MCP). Say what happened.
- One active mission at a time. Missions live in rooms named mission-<slug>.
- Keep replies here under 6 lines; the owner reads them on a phone.
- Messages that are only "ok <CODE>", "no <CODE>", "@hands ...", "!..." are not for
  the concierge or life: ignore them silently.
- When you hand work to another agent, end with one line that @mentions it.
```

### 10.6 `switch/instructions/concierge.md`
```markdown
You are the Concierge of RoomService. The owner speaks one sentence; you turn it into a
mission the crew executes. Be fast, warm, brief. Never ask more than one question.

## Ignore
Ignore silently any message that is only: "ok XXXX", "no XXXX", "@hands …", "!…",
"thanks"/"great"/"cool", or anything posted by hands, life, builder or scout in HQ.

## Mission (the owner states a goal in an HQ room)
1. slug = 2–4 lowercase words joined by "-" from the goal (e.g. volt-waitlist).
   title = under 8 words.
2. project: match the goal to these keys (keywords): volt (volt, waitlist, landing page).
   No match → none.
3. If a room "mission-<slug>" exists (list_all_rooms name_contains="mission-<slug>"),
   go to Resume. If another mission room was used in the last hour, that's fine: hands
   moves itself.
4. Template path: ON.
   - Template path: list_templates(query="roomservice-mission") → run_template(
     template_id, inputs={"slug":…, "title":…, "brief": <owner's sentence verbatim>,
     "project":…}). The template posts the kickoff.
   - Fallback path (only if run_template errors): create_room(name="mission-<slug>",
     description="RoomService mission: <title>", agent_names=["concierge","builder",
     "scout","desk-laptop","life"], instructions=<the mission-room instructions you
     know>, roles=[{"name":"hands","exclusive":true,"instructions":"The body of the
     room. Address @hands with one command per line."}]); connect_to_room(it);
     create_room_document(name="mission-brief", description="The mission as spoken",
     instructions="Read first.", content=<title + brief + slug + project>);
     post_message("@desk-laptop mission <slug> <project>\n@builder the brief is in this
     room's documents. Wait for my plan, then start.")
   If "desk-backup" is listed by list_agents, invite_agent_to_room(<mission room>,
   "desk-backup").
5. link_rooms(source_room_id=<HQ room you were addressed in>, target_room_id=<mission>,
   label="mission"); link_rooms(<mission>, <that HQ room>, "hq").
6. connect_to_room(<mission>); post_message the plan: 3–6 numbered steps, each owned by
   @builder, @scout, @life or @hands. Last line exactly "@builder go." Add a line
   "@scout <ask>" only if references would help.
7. Back in the HQ room, post exactly:
   🛎️ MISSION ACCEPTED · <title>
   Room: mission-<slug> · Crew: builder · scout · life · hands
   1. <step> 2. <step> 3. <step>
   Done when: <one line>
8. If the sentence contained everyday asks (calendar, reminder, email), post in the same
   HQ room one line: "@life <the ask, verbatim>".

## Talking to hands
hands is a program. Address it as @hands with ONE command per line, only from:
boot <project> · open <app> · url <alias|https-url> · run <script> · focus on|off ·
shot [screen|page] · say "<text>" · close <app>|all · commit "<message>" · push ·
wrap · resume <project> · status · lights on|off · release · help
Never send hands a sentence. In mission rooms use @hands. In HQ, @hands also works.

## Owner feedback during a mission
- "show me", "let me see", "screenshot" → in the mission room: "@hands shot page".
- Change requests ("make the button orange") → in the mission room: "@builder <request
  verbatim>" + one line of context. Then in HQ: "Sent to builder."
- Never send builder two messages in a row; wait for its reply first.

## Wrap up ("wrap", "wrap up", "done for today", "goodnight")
In the mission room, in order, waiting for each reply:
1. "@builder summarize today in exactly 5 bullets: done, done, not done, next, risk."
2. create_room_document (or update_room_document if you made it before) name="day-diary",
   content = date in IST + builder's bullets.
3. "@hands wrap" → hands replies with a ```json block. create/update_room_document
   name="boot-state", content = that JSON verbatim.
4. "@hands commit \"<one-line summary of today>\"" (hands asks the owner itself).
5. In HQ: "🌙 Wrapped · <title>. Diary saved. Say 'resume <project>' tomorrow."
6. "@hands say \"Day wrapped. Good night.\"" then "@hands close all".

## Resume ("resume <project or mission>")
Find mission-<slug> (list_all_rooms). load_internal_documents for "boot-state" and
"day-diary". In the mission room: "@hands resume <project>". In HQ:
"▶️ Resuming <title>. Last time, next was: <the 'next' bullet>."

## Never
Never ask the owner to type commands. Never post keys or tokens. Never address hands in
natural language. Never narrate plumbing.
```

### 10.7 `switch/instructions/builder.md`
```markdown
You are the Builder of RoomService. You write code for the mission's project.

- Projects live in ./projects/<project>/ under your directory. The project key is in the
  room document "mission-brief" (load_internal_documents).
- Wait for the concierge's plan in the mission room, then work step by step.
- The dev server is already running (hands started it); never stop it. Vite hot-reloads.
- After each visible change: post two lines (what changed, what's next), then a line
  "@hands shot page".
- Never run git commit or git push; the concierge asks hands to commit at wrap.
- Apply the owner's feedback (relayed by the concierge) before anything else.
- When asked to summarize, give exactly 5 bullets: done, done, not done, next, risk.
- End every message that hands work to another agent with an @mention line.
- Never narrate plumbing.
```

### 10.8 `switch/instructions/scout.md` (SHOULD)
```markdown
You are the Scout. When addressed in a mission room, find 3 high-quality references for
the ask (examples, docs, design inspiration). For each: create_reference(type="web",
name=<title>, description=<one line>, instructions="Use as inspiration, do not copy.",
value={"urls":[<url>]}) then attach_reference_to_room(<mission room>, <reference id>).
Post one line per reference: "<title> — <why it helps>". Then "@builder references ready."
Never narrate plumbing.
```

### 10.9 `switch/instructions/mission-room.md`
```markdown
# Mission room

This room exists for one mission. The brief is in the document "mission-brief".
The owner may not be watching this room; HQ mirrors key events to their phone.

- hands is a program holding the `hands` role. Address @hands with one grammar command
  per line. It answers with ✅ / ⛔ / ⏳ / ⚠️ receipts.
- Risky hands commands (commit, push, close all, scripts marked confirm) wait for the
  owner's approval code. Never try to approve on the owner's behalf.
- `@hands status` returns the project path and dev server URL.
- Time zone: Asia/Kolkata. Never narrate plumbing.
```

---

## 11. Runtime — Switch client layer (Lakshay, RS-03)

### 11.1 `.env.example`
```dotenv
SWITCH_URL=http://localhost:XXXX                 # Console Home → Server address
SWITCH_REGISTRATION_KEY=                         # Gateway → API Keys → type registration
ROOMSERVICE_AGENT=desk-laptop                    # desk-laptop | desk-backup
ROOMSERVICE_HQ_ROOMS=roomservice-hq,RoomService HQ
ROOMSERVICE_TZ=Asia/Kolkata
ROOMSERVICE_DESK_CONFIG=config/desk.yaml
ROOMSERVICE_DRY_RUN=false
ROOMSERVICE_HANDOFF_MODE=lease                   # lease | explicit
ROOMSERVICE_RELAY_APPROVALS=true
HUD_PORT=7777
N8N_LIFE_URL=http://localhost:5678/webhook/roomservice-life
N8N_LIFE_TOKEN=replace-with-32-random-chars
LIGHTS_ON_URL=
LIGHTS_OFF_URL=
```

### 11.2 `switch/http.py` — `SwitchHTTPClient(SwitchHTTP)`
`httpx.AsyncClient(base_url=str(SWITCH_URL).rstrip("/"), timeout=15)`; bearer = agent API key except `register`.
| Method | Request | Notes |
|---|---|---|
| `health` | `GET /health` (no auth) | True iff 200 |
| `register` | `POST /agents`, bearer = registration key, body §11.3 | 409 → `OpError(409,"exists")`; returns `(id, api_key)` |
| `list_ops` | `GET /agents/{id}/ops` | `{"operations": {...}}` |
| `op` | `POST /agents/{id}/ops/{name}`, JSON = args with `None` values removed; header `X-Switch-Connection-Id` if `conn_id` | returns `result`; 400/403/404/409 → `OpError` |
| `post` | `POST /agents/{id}/message` `{"room_id","content"}` | returns `event_id`; 429 budget, 422 guardrail → `OpError` |
| `upload` | `POST /agents/{id}/rooms/{room_id}/media` multipart: one `file` part (or repeated `files`), form `caption`, `thread_id` | max 1 file per call in our use |
| `typing` | `POST /agents/{id}/typing` `{"room_id","is_typing"}` | swallow all errors |
| `renew_lease` | `POST /agents/{id}/leases/renew` + connection header | True iff 2xx |
Retries: network errors and 5xx → 3 retries (0.3 s, 1 s, 2 s). Never retry 4xx. Logging redacts `Authorization`.

### 11.3 Registration body (`roomservice register`)
```json
{
  "name": "desk-laptop",
  "display_name": "Hands · laptop",
  "description": "RoomService desk agent. Acts on this computer through an allowlist. Speaks the hands grammar only.",
  "connector_type": "roomservice-desk",
  "integration_profile": {
    "connection_model": "always_on",
    "message_exchange": true,
    "pre_invocation_mediation": [],
    "post_invocation_mediation": [],
    "event_reporting": []
  }
}
```
`life`: display `Life`, connector_type `roomservice-life`, description "Calendar and email through n8n. Creates events and drafts; never sends email." `desk-backup`: display `Hands · backup`.
Then `op("update_agent_detail", {"agent_id": id, "addressing": "owner_and_owner_agents"})`.
Store in `~/.roomservice/agents.json` (chmod 600): `{"<switch_url>": {"<name>": {"id": "...", "api_key": "..."}}}`. Never print keys. CLI: `roomservice register [--agent desk-laptop|life|desk-backup|all] [--overwrite]`; default `all` on the demo machine = `desk-laptop` + `life`. Prints the `!invite-agent` lines afterwards.

### 11.4 `switch/connection.py` — `RoomConnection` (one WebSocket per room)
- URL: `ws[s]://<host>/agents/{agent_id}/connection/ws?connection_id=<uuid>&scope=single&filter=all&rooms=<room_id>&start_from=<cursor|head>[&expected_generation=<g>]&client=roomservice&client_version=1.0.0`
- `connect(url, additional_headers={"Authorization": f"Bearer {key}"}, open_timeout=10, ping_interval=None, max_size=8*2**20)` — WebSocket-level pings off; Switch uses JSON ping frames.
- `connection_id`: UUID per (agent, room) persisted in `~/.roomservice/cursors.json` with `generation` and `cursor`.
- **Receive task:** for each JSON text frame:
  - `{"type":"ping"}` (control frames may come as `{"type": ...}` or `{"event": ...}` — accept either key) → **immediately** `send({"type":"pong","cursor":cursor})` before anything else.
  - `connection_state` → save `generation`, `cursor`, `rooms`.
  - domain event (has `id` and `data.type` in message/command/room_join) → skip if `id <= cursor`; else enqueue to the handler queue.
  - `gap` → `cursor = resumed_at`; set `gap_pending`; before handling the next event call `op("read_context", {"limit": 20}, conn_id)` (result logged only).
  - `evicted`: `taken_over` → stop permanently + HUD `system` error; `heartbeat_lapsed` | `no_stream` | `unfenced` | `connection_error` → reconnect; `closed` → reconnect once after 5 s, then stop.
  - `subscription_changed` without our room → close this connection.
  - `room_released` → mark role lost in this room; HUD `system` warn.
  - `refused` → log status/detail; close.
- **Handler task:** drains queue serially; after the handler returns, `cursor = id` and persist (debounced 1 s).
- Close codes: 4401 → fatal (bad key); 4409 → fatal unless detail mentions lapse; 4403 → fatal for this room; 1000/1011/1012/abnormal → reconnect.
- Backoff: 0.5, 1, 2, 4, 8, 10, 10… s, ±20% jitter; reset after 30 s healthy.
- After each (re)open: `op("connect_to_room", {"room_id": rid}, conn_id)` → store instructions, participants, roles.

### 11.5 `switch/rooms.py` — `RoomWatcher`
- Every 3 s: `op("list_rooms")` (no connection header). Diff → open/close `RoomConnection`s. HUD `system` info `room opened: <name>`.
- Kind: `hq` if name or id in `ROOMSERVICE_HQ_ROOMS`; `mission` if name starts with `mission-`; else `other`.
- Cap 30 connections: keep all HQ + 28 most recently active missions.

### 11.6 `agents/base.py` — `BaseProtocolAgent(ProtocolAgent)`
- Loads key from `agents.json` for `name` and current `SWITCH_URL`; missing → exit with "Run `uv run roomservice register` first".
- Dedupe: LRU of 2,000 `message_id`s.
- Self id: from `connect_to_room` participants, the entry whose name equals `self.name`; messages with `sender == self_id` are ignored.
- Publishes every message event in every room to the HUD bus (`message` event; `agent` resolved from `sender_name`: crew names → key; paired owner → `you`; else `other`).
- `on_message` is called only when `payload.addressed` is true **or** the subclass declares `wants_unaddressed(room, msg) -> bool` true (desk uses this for ignition, approvals and relay).
- Telegram/Mattermost length: truncate any outgoing body to 3,500 chars + "…".

### 11.7 Replies, media, typing
- `reply()` → `op("post_message", {"body": text, "thread_id": thread_id}, room.conn_id)`; if `OpError` 409 (dead connection) → fallback `post(room.id, text)`.
- `upload()` → `upload(room.id, [(filename, png, "image/png")], caption, thread_id)`.
- Any desk command > 300 ms: `typing(room, True)` before, `typing(room, False)` after.

### 11.8 Spikes module (`spikes.py`, `roomservice spike s0..s8`) — see §20.1.

### 11.9 CLI (`cli.py`, typer)
| Command | Ticket | Does |
|---|---|---|
| `roomservice register [--agent] [--overwrite]` | RS-03 | §11.3 |
| `roomservice spike <s0..s8>` | RS-03 | §20.1 |
| `roomservice pair` | RS-07 | §9.5 |
| `roomservice up [--dry-run] [--no-hud] [--no-life]` | RS-07 | starts desk (+life, relay, scheduler, HUD) |
| `roomservice backup [--dry-run]` | RS-12 | `up` as `desk-backup`, no life/scheduler |
| `roomservice say "<text>"` | RS-07 | local TTS test |
| `roomservice doctor` | RS-07 (+RS-14) | §20.7 |
| `roomservice build-templates` | RS-04 | §10.2 |
| `roomservice hud --demo` | RS-08 | HUD server + scripted fake events, no Switch |

---

## 12. Desk agent — hands (Lakshay, RS-05 + RS-07)

### 12.1 Responsibilities
Parse → allowlist → approvals → execute via OS adapter → receipts → HUD events → speech. Plus ignition, relay hooks, role handling.

### 12.2 Grammar (`desk/grammar.py`)
- Split body into lines; strip. A line is a command if it matches (case-insensitive):
  `^@(?:hands|desk-laptop|desk-backup)[,:]?\s+(?P<cmd>.+)$`
- If the message is addressed and no line matches, treat the whole body with all `@\S+` tokens removed as one command.
- Tokenize `cmd` with `shlex.split` (posix); unbalanced quotes → `ParseError`.
- First token lowercased then alias-mapped: `screenshot|show|snap|show-me → shot`, `speak → say`, `start → boot`, `goodnight → wrap`, `stop|halt → freeze`, `approve|yes → ok`, `deny|reject → no`.
- Max 5 commands per message; extras → `⛔ refused · more than 5 commands in one message`.
- Output: `Command(verb: str, args: list[str], raw: str)` or `ParseError(raw, reason)`.

### 12.3 Verbs
| Verb | Args | Effect | Approval | Owner-only |
|---|---|---|---|---|
| `boot` | `<project>` | run project profile (§12.5) | — | — |
| `mission` | `<slug> <project|none>` | set active mission; release role elsewhere; `assume_role(hands)` here; boot project if not booted this process; speak; HUD `mission` | — | — |
| `open` | `<app-key>` | open allowlisted app | — | — |
| `url` | `<alias>` or URL | open in browser (allowed: `https://*`, `http://localhost:*`, `http://127.0.0.1:*`) | — | — |
| `run` | `<script-key>` | run script; receipt includes exit code + last 15 lines | if `confirm` | — |
| `focus` | `on|off` | OS focus | — | — |
| `shot` | `[screen|page]` (default: `page` if active project has `screenshot_url`, else `screen`) | upload PNG to this room; relay mirrors | — | — |
| `say` | `"<text>"` (≤ 200 chars) | speak + HUD `speak` | — | — |
| `close` | `<app-key>` or `all` | quit app(s); `all` = apps opened this mission | `all` | — |
| `commit` | `"<message>"` | `git add -A`, `git commit -m <message>` in project | yes | — |
| `push` | — | `git push` (no force) | yes | — |
| `wrap` | — | write state file, reply JSON (§12.8) | — | — |
| `resume` | `<project>` | boot from newest state (§12.8) | — | — |
| `status` | — | mission, project path, dev URL, opened apps, uptime, queue length, frozen, role held | — | — |
| `lights` | `on|off` | webhook or HUD flash | — | — |
| `release` | — | release `hands` role (handoff fallback) | — | — |
| `pair` | `<6 digits>` | §9.5 | — | (pairing code) |
| `ok` / `no` | `<CODE>` | resolve approval | — | yes |
| `freeze` / `unfreeze` | — | stop / resume executing | — | yes |
| `help` | — | grammar summary (≤ 12 lines) | — | — |

### 12.4 Execution model
- Single `asyncio.Queue`, serial execution. Busy → immediate `⏳ queued · <raw> (busy with <current>)`.
- Rate limit 20 executed commands / rolling 60 s → `⛔ refused · rate limit (20/min)`.
- Frozen → everything except `unfreeze`, `status`, `help` → `⛔ refused · frozen by owner`.
- HUD `action_start`/`action_end` with `ms` for every executed command.
- Dry-run adapter (`desk/os/dry.py`): logs, sleeps 150 ms, succeeds; screenshots are a generated 1280×800 PNG (dark background, text "DRY RUN · <verb> · HH:MM:SS").

### 12.5 Boot profile execution order (`boot <project>`)
1. `lights on` if `project.lights` (webhook if `LIGHTS_ON_URL`, else HUD `ignition` with `lights:"flash"` only if not already ignited this minute).
2. `open_in_editor(path)` if `open_editor` (uses `code` CLI everywhere; if `code` missing → open `apps.editor`).
3. For each terminal: `open_terminal(path, cmd, name)`.
4. `wait_for` URL: poll GET every 1 s up to 45 s (don't fail boot on timeout; note it in receipt).
5. Open each URL (alias → `urls[alias]`).
6. `focus(on=True)` if `focus`.
7. Music: if `music` starts with `spotify:` → `open_url(music)`; else `open_app(apps.music)`.
8. Record opened apps/urls/terminals in mission state.
Receipt: `✅ boot volt · editor, 1 terminal, 2 tabs, focus, music · 3.4s` (list only what happened; failures appended as `· ⚠ focus unsupported`).

### 12.6 `desk.example.yaml` (Yash fills real values in RS-06; schema = §8.1)
```yaml
version: 1
machine_name: laptop
timezone: Asia/Kolkata
voice: {enabled: true, voice_name: Samantha, rate: 190}
ignition:
  wake_phrases: ["room service", "roomservice", "room servis", "rumservice", "room sarvis"]
  default_profile: focus-session
apps:
  editor:   {mac: "Visual Studio Code", win: "code", linux: "code"}
  browser:  {mac: "Google Chrome", win: "chrome", linux: "google-chrome"}
  music:    {mac: "Spotify", win: "spotify", linux: "spotify"}
  notes:    {mac: "Notes", win: "notepad", linux: "gedit"}
  terminal: {mac: "Terminal", win: "wt", linux: "x-terminal-emulator"}
urls:
  github: https://github.com
  calendar: https://calendar.google.com
  mail: https://mail.google.com
scripts:
  test:   {cmd: ["npm", "test"], cwd: project, confirm: false, timeout_s: 120}
  build:  {cmd: ["npm", "run", "build"], cwd: project, confirm: false, timeout_s: 180}
  deploy: {cmd: ["npx", "vercel", "--prod", "--yes"], cwd: project, confirm: true, timeout_s: 300}
projects:
  volt:
    keywords: ["volt", "waitlist"]
    path: ~/roomservice-workspace/projects/volt
    open_editor: true
    terminals: [{name: dev, cmd: "npm run dev -- --port 5173 --strictPort"}]
    urls: ["http://localhost:5173", github]
    wait_for: http://localhost:5173
    screenshot_url: http://localhost:5173
    focus: true
    music: "spotify:playlist:37i9dQZF1DX5trt9i14X7j"
    lights: true
profiles:
  focus-session: {apps: [notes], urls: [calendar], focus: true, lights: true, music: "spotify:playlist:37i9dQZF1DX5trt9i14X7j"}
schedule: {morning_brief: "08:55", morning_days: "mon-sat", wrap_nudge: "23:00"}
limits: {actions_per_minute: 20, max_commands_per_message: 5, approval_ttl_s: 300}
```

### 12.7 OS adapters (`desk/os/*`)
All subprocesses via `asyncio.create_subprocess_exec(*argv)` — **never a shell**, except `open_terminal`, whose `cmd` comes only from config.
| Op | macOS | Windows | Linux |
|---|---|---|---|
| open_app | `open -a <name>` | `cmd /c start "" <name>` | `Popen([name], start_new_session=True)` |
| quit_app | `osascript -e 'quit app "<name>"'` | `taskkill /IM <name>.exe /F` | `pkill -f <name>` |
| open_url | `open <url>` | `cmd /c start "" <url>` | `xdg-open <url>` |
| open_in_editor | `code <path>` | `code <path>` (`code.cmd`) | `code <path>` |
| open_terminal | `osascript -e 'tell application "Terminal" to do script "cd <q(cwd)> && <cmd>"' -e 'tell application "Terminal" to activate'` | `wt -d <cwd> cmd /k <cmd>` | `x-terminal-emulator -e bash -lc "cd <q(cwd)> && <cmd>; exec bash"` |
| focus | `shortcuts run "RoomService Focus On"` / `"RoomService Focus Off"` (exit≠0 → False) | False | False |
| screenshot | `mss` monitor 1 → PNG | same | same |
| speak | `say -v <voice> -r <rate> <text>` | PowerShell `Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('<text>')` | `espeak <text>` |
`q()` = `shlex.quote`. Page screenshot (SHOULD, RS-10): Playwright chromium headless, viewport 1440×900, `device_scale_factor=2`, `wait_until="networkidle"`, timeout 15 s → on failure fall back to screen shot with caption suffix `(screen fallback)`.
**macOS permissions** (RS-06 documents, RS-07 doctor checks): Screen Recording for the terminal app running `roomservice` (else screenshots are black/wallpaper only); Automation → Terminal (first `open_terminal` prompts; click OK); create Shortcuts "RoomService Focus On"/"… Off" (action: Set Focus → Do Not Disturb On/Off).

### 12.8 Mission state, wrap, resume (`desk/state.py`)
State dir `~/.roomservice/state/`. Active mission in memory + `active.json`. `wrap` writes `<slug>.json` and replies:
````
✅ wrap · volt-waitlist · 96 min
```json
{"slug":"volt-waitlist","project":"volt","wrapped_at":"2026-11-07T22:41:05+05:30","mission_minutes":96,"path":"~/roomservice-workspace/projects/volt","git":{"branch":"main","head":"3f2a91c","dirty_files":2},"opened":{"apps":["music"],"urls":["http://localhost:5173","https://github.com"],"terminals":["dev"]},"screenshot_url":"http://localhost:5173"}
```
````
`resume <project>`: newest state file with that project → `boot <project>` (skipped if this process already booted that project, e.g. by ignition from "room service, resume volt") + any extra `opened.urls` not already opened → `✅ resume volt · editor, 1 terminal, 2 tabs · last head 3f2a91c`. No state → behaves as `boot` with note `· no saved state`. A project counts as booted for the lifetime of the process until `close all` or `wrap`.
Starting a new `mission` while another is active: auto-wrap the old one silently (state file only, no commit), release role, then proceed.

### 12.9 Ignition (`desk/ignition.py`)
- `wants_unaddressed` true for HQ messages from a **paired owner** containing a wake phrase (case-insensitive, punctuation stripped). Dedupe by message id; at most one ignition per 60 s.
- Steps (first visible action ≤ 3 s): HUD `ignition` (lights `webhook` if `LIGHTS_ON_URL` else `flash`) + webhook call; `say` greeting by IST hour (05–11 "Morning", 12–16 "Afternoon", else "Evening") + `". Booting <Project>."` (non-blocking); project = first whose keyword appears in body → `boot <project>`, else `default_profile`; post in that HQ room `⚡ ignition · booting volt` (or `focus-session`).
- Later `mission <slug> volt` sees volt booted in this process → skips boot: `✅ mission volt-waitlist · already booted · hands assumed`.

### 12.10 Approvals (`desk/approvals.py`)
- Code: 4 chars from `ACDEFGHJKMNPQRTUVWXY3479`, unique among open ones; TTL `approval_ttl_s` (300).
- Created for: `commit`, `push`, `close all`, `run` with `confirm`, and builder relay (§13.3).
- Posted in the requesting room (and mirrored to HQ by relay) as:
```
⚠️ approval needed · commit "waitlist page v1" in volt
Owner: reply  ok K7Q3  or  no K7Q3  (5 min)
```
- Resolution: any message, in any covered room, from a **paired owner** whose stripped text matches `^(?:@\S+\s+)?(ok|no|approve|yes|deny|reject)\s+([A-Z0-9]{4})$` (case-insensitive). Unaddressed is fine (`wants_unaddressed` true for these). Agent senders never resolve.
- Results: `✅ approved by <sender_name> · <result summary> · <ms>` / `🚫 declined by <sender_name> · <cmd>` / `⌛ expired · <CODE> · <cmd>`. HUD `approval_open/closed`; speak "Approval needed." on open.

### 12.11 Receipt formats (`desk/receipts.py`, exact; snapshot-tested)
```
✅ <verb> <args> · <summary> · <s>s
⏳ queued · <raw> (busy with <current raw>)
⛔ refused · <raw> — <reason>
⛔ didn't understand · "<line>" · try: @hands help
⚠️ approval needed · <cmd> in <project>\nOwner: reply  ok <CODE>  or  no <CODE>  (5 min)
✅ approved by <name> · <summary> · <s>s
🚫 declined by <name> · <cmd>
⌛ expired · <CODE> · <cmd>
📸 <project|screen> · <url or "screen"> · <HH:MM> IST           (screenshot caption)
⚡ ignition · booting <project|profile>
🫱 hands is now on <agent name>
🔐 paired · <sender_name> on <room name>
🧊 frozen by <name> / 🔥 unfrozen by <name>
```
Seconds with one decimal.

---

## 13. Relay and phone experience (Lakshay, RS-10)

### 13.1 Why
Mission rooms are on Mattermost (Telegram bots can't create groups). The phone lives in Telegram HQ. The desk already reads every message in rooms it covers.

### 13.2 Mirror rules (`relay.py`), mission → every HQ room via `post()` / `upload()`
| Trigger (in a `mission-*` room) | Mirrored as |
|---|---|
| First message by `concierge` after kickoff | `🧭 plan · mission-<slug>` + its first 6 lines |
| Desk uploads a screenshot | same PNG + caption |
| Desk `⚠️ approval needed` | same text |
| Builder permission request (§13.3) | `⚠️ builder asks · <one-line summary>` + `Owner: reply  ok <CODE>  or  no <CODE>` |
| `builder` message containing whole word `done` or `finished` | `🛠️ builder · <first line>` |
| Desk `✅ wrap` | `🌙 wrapped · mission-<slug> · <minutes> min` |
Rate limit: 6 mirrors/min/mission; overflow → one `… +N updates in mission-<slug>` per minute.

### 13.3 Builder approval relay **[SPIKE S5]** (behind `ROOMSERVICE_RELAY_APPROVALS`)
- Detect: message in a mission room from `builder` or posted by Switch on builder's behalf, containing `Allow once` or `Allow for this session` (S5 captures a real one into `tests/fixtures/permission_request.json` and finalizes the regex).
- Create approval bound to `{room_id, thread_id or message_id}`; mirror. On `ok CODE` → desk posts exactly `yes` in that thread (`reply(room, "yes", thread_id)`); `no CODE` → `no`.
- S5 fails → set `ROOMSERVICE_RELAY_APPROVALS=false`: mirror text becomes `⚠️ builder asks · <summary> — approve on the laptop`; demo relies on desk's own approvals.

### 13.4 Phone rules
Every HQ message ≤ 6 lines; screenshots always captioned; approval codes on their own line.

---

## 14. Life agent, n8n, scheduler (Yash, RS-11)

### 14.1 `infra/docker-compose.n8n.yml`
```yaml
services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:latest
    restart: unless-stopped
    ports: ["5678:5678"]
    environment:
      - N8N_HOST=localhost
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=http://localhost:5678/
      - GENERIC_TIMEZONE=Asia/Kolkata
      - TZ=Asia/Kolkata
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - N8N_SECURE_COOKIE=false
    volumes: [n8n_data:/home/node/.n8n]
volumes: {n8n_data: {}}
```
`N8N_ENCRYPTION_KEY` in `infra/.env` (git-ignored; 32 random chars). Start: `docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d`. Open `http://localhost:5678` (always via localhost so OAuth redirect matches).

### 14.2 Workflow `RoomService Life` (build in editor → export to `n8n/life.workflow.json` without credentials → **Activate** the workflow; production URL is `/webhook/roomservice-life`)
1. **Webhook**: POST, path `roomservice-life`, Authentication = Header Auth credential (name `X-RoomService-Token`, value = `N8N_LIFE_TOKEN`), Respond = "Using 'Respond to Webhook' node".
2. **Edit Fields (Set)**: `text, sender_name, room_name, mission_slug, now_iso, tz, mode` from `{{$json.body.*}}`.
3. **AI Agent** (Tools Agent), system message:
   ```
   You are Life, RoomService's calendar and email agent. Owner time zone: {{ $json.tz }}.
   Now: {{ $json.now_iso }}. You can read and create Google Calendar events, read recent
   Gmail messages, and create Gmail DRAFTS. You must never send email. Reply in at most
   4 short lines. If you created something, end with "LINK: <url>".
   If mode is "brief": today's events, then the 3 most important unread emails.
   ```
   User message: `{{ $json.text }}`. Chat model per §6. Memory: Simple Memory, session key `{{ $json.room_name }}`, context window 10.
   Tools: Google Calendar Tool (Get Many; Create), Gmail Tool (Get Many, limit 10, unread; Create Draft). **No send tool exists.**
4. **Respond to Webhook**: JSON `{"reply": "{{ $json.output }}"}`.
Credentials: Google Cloud project → enable Calendar + Gmail APIs → OAuth client (Web) with redirect `http://localhost:5678/rest/oauth2-credential/callback` → add test user (owner's Gmail) → create n8n Google Calendar OAuth2 + Gmail OAuth2 credentials. Anthropic or OpenAI API credential.
Fallback (if OAuth not ready by 19:30): replace both tools with a **Code Tool** returning `"calendar not connected yet; I would: " + query`. README states it.

### 14.3 `agents/life.py` — `LifeAgent(BaseProtocolAgent)`, name `life`
- On addressed message: typing on; HUD `agent_state life working`; `POST N8N_LIFE_URL` header `X-RoomService-Token`, JSON `{text (mentions removed), sender_name, room_name, mission_slug (active or null), now_iso (IST), tz:"Asia/Kolkata", mode:"ask"}`, timeout 60 s.
- 200 → reply `🗓️ ` + `reply`. Else → `⛔ life · n8n not reachable at <url>. Start it: docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d`. HUD state idle.
- Runs inside `roomservice up` with its own registration and connections (separate `RoomWatcher`).

### 14.4 Scheduler (`scheduler.py`, APScheduler, tz Asia/Kolkata)
| Job | When | Action |
|---|---|---|
| `morning-brief` | `schedule.morning_days` at `schedule.morning_brief` | life calls n8n `mode:"brief"`, posts in every HQ room `☀️ Morning brief` + reply |
| `wrap-nudge` | daily at `schedule.wrap_nudge`, only if a mission is active | desk posts in HQ `🌙 It's <HH:MM>. Say "wrap up" when you're done.` and speaks it |
`roomservice up --fire morning-brief` triggers a job immediately (for testing/demo).

---

## 15. Roles and handoff (Lakshay, RS-12)

- An agent holds one role at a time across all rooms → one active mission per desk.
- `mission` verb: if holding `hands` elsewhere → `op("release_role", {}, old_conn)`; then `op("assume_role", {"role":"hands"}, conn)`. If assume fails because someone else holds it (409/error text mentions held) → receipt `⛔ refused · hands is held by <holder from list_roles>`.
- While holding: `renew_lease(conn)` every 3 s; 3 consecutive failures → role lost, HUD warn.
- **Backup (`agents/backup.py`, `roomservice backup`)**: same DeskAgent with its own desk.yaml (`machine_name: backup`), no life/scheduler. Every 5 s, for the newest `mission-*` room it's a member of: `list_roles` → if `hands` unheld (or `ROOMSERVICE_HANDOFF_MODE=lease` and assume succeeds) → `assume_role` → post `🫱 hands is now on desk-backup` in mission + HQ, HUD `transfer` (both machines' HUDs: the laptop's shows it when it reconnects).
- **[SPIKE S8]** lease lapse time after the laptop runtime is killed. ≤ 15 s → `lease` mode. Otherwise `explicit` mode: demo uses `@hands release` from the owner on camera before closing the lid (still shows the role moving).

---

## 16. Mission Control HUD (Yash, RS-08)

### 16.1 Server (`hud/server.py`)
FastAPI on `127.0.0.1:HUD_PORT`. Routes: `GET /` → `static/index.html`; static files; `GET /shots/{file}` from `~/.roomservice/shots/` (filename regex `^shot-[a-z0-9-]+-\d{6}\.png$`); `GET /api/state` → `hello`; `POST /api/freeze {"on":bool}` → calls desk freeze (only from 127.0.0.1); `WS /ws` → sends `hello` then streams `bus.subscribe()`. `hud/demo.py`: `roomservice hud --demo` publishes a scripted 90-s loop of every event type (ignition → mission → messages → actions → approval → screenshot (bundled sample PNG) → transfer → wrap) for building the UI without Switch.
Auto-open (in `up`): macOS `open -na "Google Chrome" --args --app=http://127.0.0.1:7777 --start-fullscreen` if Chrome exists, else `webbrowser.open`.

### 16.2 Layout (1920×1080 reference; works down to 1280×720)
```
┌────────────────────────────────────────────────────────────────────────────┐
│ ROOMSERVICE ▪ mission-volt-waitlist     ⏱ 00:41:12    ● switch ● n8n ● hands │ 56px
├──────────────┬──────────────────────────────────────────┬──────────────────┤
│ CREW  (300)  │              ORB (canvas 420px)          │ FEED (420)        │
│ ◉ You        │       breathing; pulses in the colour    │ 14:31 you  …     │
│ ◉ Concierge  │       of whoever just spoke              │ 14:31 conc …     │
│ ◉ Builder    │                                          │ 14:32 hands ✅    │
│ ◉ Scout      │   caption: last spoken line (28px)       │ (newest at top,   │
│ ◉ Hands      │                                          │  max 60 items)    │
│ ◉ Life       │                                          │                   │
├──────────────┴──────────────────────────────────────────┴──────────────────┤
│ HANDS ▸ [boot volt 3.4s] [shot page 1.2s] [commit ⚠ K7Q3 4:12] …  (120px)    │
└────────────────────────────────────────────────────────────────────────────┘
```
Overlays: approval card (centre, code 64px mono, countdown ring), screenshot toast (bottom-right, 6 s), transfer banner ("HANDS TRANSFERRED → desk-backup", 4 s), freeze banner (red, persistent), ignition sequence.

### 16.3 Visual language
- Background `#05070B`; 48-px grid `rgba(120,160,255,0.06)`; radial vignette.
- Type: Space Grotesk 600 headings; JetBrains Mono feed/receipts.
- Orb (Canvas 2D, 60 fps): 3 concentric rings + 120-particle halo. Idle breathing ±3% at 0.25 Hz. `message` from X → ring flashes X's colour (400 ms ease-out). `action_start` → hands-colour arc sweeps until `action_end`. `approval_open` → slow red pulse.
- Crew lights: offline `#3A4250`; idle = colour at 35%; working = colour, 1.2-s pulse; needs_you = `#FF3B3B`, 0.6-s pulse.
- Agent state rules (in the HUD, from events): all crew start `idle` after `hello`; `message` addressed to X (body contains `@<x>` or role `@hands`) → X `working`; `message` from X → X `idle`; `action_start/end` → hands working/idle; `approval_open` → you `needs_you` until closed; no event for X in 10 min while working → idle.
- Ignition (1.6 s): lights-flash (white 85% → 0, 700 ms, only when `lights:"flash"`) → scan line top→bottom (400 ms) → grid fades in (300 ms) → orb scales 0→1 with overshoot (600 ms) → "ROOM SERVICE ONLINE" types in (300 ms).
- Sound (`sfx.js`, Web Audio, synthesized): ignition sine sweep 220→880 Hz/600 ms; message 2-note blip; approval two low pulses; screenshot shutter (80 ms filtered noise); transfer whoosh (noise + low-pass sweep). Audio unlocks on first key/click; `M` mutes.
- Keys: `F` fullscreen, `M` mute, `S` freeze toggle (`/api/freeze`), `C` demo captions on/off.
- Reconnect: if `/ws` closes, show "reconnecting…" pill and retry every 1 s.

---

## 17. Security model (README section "What hands will never do")
| Threat | Control |
|---|---|
| Prompt injection makes desk run arbitrary code | No shell from chat; allowlisted apps, URL patterns, script keys only; args never reach a shell |
| Someone else commands the desk | Switch addressing `owner_and_owner_agents` refuses others before the desk sees an addressed message |
| An agent approves its own risky action | Approvals resolve only from paired owner participant ids; agents can't pair |
| Display-name spoofing | Identity = exact participant id captured by pairing |
| Runaway loop | 20 actions/min, 5 commands/message, serial queue, `freeze` (chat or HUD `S`) |
| Secrets leak | Keys only in `.env`, `infra/.env`, `~/.roomservice/agents.json` (600); logs redact `Authorization`, `api_key`, `token` |
| Destructive git | commit/push need approval; never `--force`, `reset`, `rm` |
| Email sent by mistake | No send tool in n8n workflow |
| `file://` / `javascript:` URLs | URL verb accepts only https + localhost http |
| HUD API abuse | HUD binds 127.0.0.1 only; `/api/freeze` rejects non-loopback |

---

## 18. Seed project and setup scripts (Yash, RS-06)

### 18.1 `demo/volt`
Vite 5 + TS, one page: headline "Volt — power for small teams", sub-line, email input, "Join the waitlist" button, counter "128 people waiting", footer. Plain CSS variables `--brand:#3B5BFF; --cta-bg:var(--brand)`. `package.json` scripts: `dev` = `vite`, `build` = `vite build`, `test` = `node -e "console.log('ok')"`. `npm run dev -- --port 5173 --strictPort` must start < 5 s. Intentionally plain so "orange, bigger, confetti" is visible.

### 18.2 `scripts/setup_mac.sh` (idempotent)
Checks: macOS, `brew`, `uv`, Node ≥ 20, Docker running, `code` CLI (prints the VS Code "Shell Command: Install 'code' command in PATH" hint if missing). Then: `mkdir -p ~/roomservice-workspace/{concierge,scout,projects}`; copy `demo/volt` → `~/roomservice-workspace/projects/volt` if absent; `npm install`; `git init`, `git config user.name "RoomService"`, `git config user.email "roomservice@local"`, initial commit; `cp -n config/desk.example.yaml config/desk.yaml`; `cp -n .env.example .env`; `uv sync`; `uv run playwright install chromium`; prints the macOS permission checklist (§12.7). `scripts/setup_windows.ps1` does the equivalent minus macOS items.

---

## 19. Observability and errors
- Logs: rich console + JSON lines at `~/.roomservice/logs/runtime.jsonl` (`ts, level, agent, room, event, msg`). Never log message bodies longer than 400 chars or any key.
- Every user-visible error is one line with the fix (e.g. n8n start command). No stack traces in chat.
- `roomservice up` prints a status table every 60 s in the terminal (rooms, role held, queue, last error).

---

## 20. Testing

### 20.1 Spikes (`roomservice spike <id>`; run in Phase 0–1; results go in `DECISIONS.md`)
| ID | Question | Script | Pass | Fallback |
|---|---|---|---|---|
| S0 | Second machine reaches server? | `GET $SWITCH_URL/health` from 2nd machine | 200 | SSH port forward (§5.2) |
| S1 | Base URL right? | `GET /health` | 200 | fix `SWITCH_URL` |
| S2 | Register + WS + ping | register `rs-spike`, open WS on HQ, answer pings 30 s | `connection_state`, no eviction | check key type / scheme / `additional_headers` |
| S3 | Post + media | `post()` text + `upload()` PNG to HQ | visible in Mattermost (and Telegram later) | text-only receipts; screenshot only on HUD |
| S4 | Agent-run mission template | owner says "test mission spike room" in HQ | `mission-spike-room` with crew, brief doc, kickoff received by desk | concierge fallback path (§10.4) |
| S5 | Agent "yes" answers builder permission | builder asked to `npm i left-pad` in a mission room; desk posts `yes` | builder proceeds | `ROOMSERVICE_RELAY_APPROVALS=false` |
| S6 | New room visible ≤ 5 s | create room; watch logs | `room opened` | poll every 2 s |
| S7 | `@hands` reaches the holder (mission) and alias works (HQ) | after assume, post `@hands status` in both | `addressed=true` | accept `@hands` lines when holder per `list_roles` |
| S8 | Lease lapse time | kill laptop runtime; backup polling | backup holds role ≤ 15 s | `ROOMSERVICE_HANDOFF_MODE=explicit` |

### 20.2 Unit tests (`tests/unit/`, CI, no network)
- `test_config.py`: valid example loads; unknown key error names the YAML path; `~` expansion.
- `test_grammar.py` (≥ 40 cases): each verb; quotes/escapes; aliases; multi-line; > 5 commands; mention variants (`@hands,` `@HANDS:` `@desk-laptop`); unbalanced quotes; empty.
- `test_allowlist.py`: https ok; localhost/127.0.0.1 http ok; `file:`, `javascript:`, `http://example.com` denied; unknown app/script.
- `test_approvals.py` (freezegun): alphabet, uniqueness, TTL, owner-only, agent cannot resolve, resolution from any room, regex variants.
- `test_ignition.py`: phrase variants, owner-only, keyword match, default profile, 60-s cooldown, dedupe.
- `test_desk_queue.py`: serial order, queued receipt, rate limit, freeze/unfreeze.
- `test_receipts.py`: every format of §12.11 (snapshot strings).
- `test_state.py`: wrap JSON shape; resume picks newest; auto-wrap on new mission.
- `test_relay.py`: each rule; rate-limit collapse.
- `test_os_adapters.py`: argv per OS (subprocess mocked); `q()` quoting.
- `test_templates_build.py`: placeholder replaced, literal blocks, missing file error.
- `test_hud_events.py`: every event model round-trips JSON.

### 20.3 Contract tests (`tests/contract/`, CI) with `fake_switch.py`
FastAPI + websockets fake: `/health`, `POST /agents`, `GET/POST /agents/{id}/ops[/name]` (`list_rooms`, `connect_to_room`, `post_message`, `assume_role`, `release_role`, `list_roles`, `list_participants`, `read_context`, `update_agent_detail`), `/message`, `/rooms/{rid}/media`, `/typing`, `/leases/renew`; WS sends `connection_state`, `ping` every 0.2 s, scripted domain frames, `evicted`, `gap`. Records every call for assertions.
Tests: pong within 100 ms while a 2-s handler runs · resume uses `start_from`+`expected_generation`, no duplicate execution · `taken_over` stops · `heartbeat_lapsed` reconnects · `gap` → `read_context` first · full desk flow `@hands boot volt` (dry) → receipts in order + HUD events · mission flow → release old + assume new + renew every 3 s · life → respx-mocked n8n → reply.

### 20.4 Live tests (`pytest -m live`, need real Switch + `.env`)
L1 register (`rs-live-test`, overwrite), connect, post, upload, typing · L2 `@hands status` round trip < 2 s · L3 concierge mission room < 75 s · L4 life → n8n → reply < 20 s.

### 20.5 Acceptance runbook (Phase 5; run 3× clean before recording; all must pass)
| # | Do | Expect | Limit |
|---|---|---|---|
| A1 | Telegram HQ: "Room service, tonight we ship the Volt waitlist page" | HUD ignition + voice + VS Code | first visible ≤ 3 s |
| A2 | — | `✅ boot volt` receipt in HQ | ≤ 12 s |
| A3 | — | mission card in HQ; `mission-volt-waitlist` in Mattermost with crew + brief | ≤ 75 s |
| A4 | `!roles` in mission | hands → desk-laptop | — |
| A5 | "show me" | screenshot in HQ with caption | ≤ 15 s |
| A6 | "make the join button orange and bigger" | builder edits; new screenshot mirrored | ≤ 120 s |
| A7 | "block nine to eleven tonight for this and remind me at eleven" | life reply with LINK; event in Google Calendar | ≤ 25 s |
| A8 | builder permission request | mirrored; `ok CODE` → proceeds (or "approve on laptop" if S5 fallback) | ≤ 10 s |
| A9 | kill laptop runtime / close lid | `🫱 hands is now on desk-backup` | ≤ 15 s (lease) |
| A10 | "wrap up" | diary + boot-state docs; approval; `ok` → commit; goodnight; apps close | ≤ 120 s |
| A11 | "room service, resume volt" | restore + resume card | ≤ 15 s |
| A12 | non-owner account: "@hands close all" | nothing happens (Switch refuses) | — |
| A13 | "@hands open Steam" | `⛔ refused · open Steam — not on the allowlist` | — |
| A14 | HUD `S` | freeze banner; commands refused until unfreeze | — |

### 20.6 Chaos
Restart Switch mid-mission → reconnect, no duplicates · stop n8n → life error line only · Wi-Fi off 20 s → resume.

### 20.7 Doctor (`roomservice doctor`) — ✅/❌ with fix hint for each
Switch health · registration key valid · agents.json for this server · each agent key (`GET /ops`) · rooms visible (lists all, marks HQ) · owners paired · desk.yaml valid · project paths exist · `code` on PATH · Chrome/Spotify installed · Screen Recording works (non-black screenshot heuristic: >2% non-dark pixels) · `shortcuts` focus shortcuts exist (mac) · n8n reachable + token valid (`mode:"ask"`, text "ping") · Playwright chromium · TTS · HUD port free.

---

## 21. Demo video (2:45) and fallback

Setup: HUD on the laptop screen (or external monitor), Mattermost visible on second screen or alt-tab; phone mirrored (iPhone: QuickTime → New Movie Recording → iPhone; Android: `scrcpy`). OBS: phone 30% left, desk 70% right. Lights dim at start.

| Time | Shot | Words / action | Checks |
|---|---|---|---|
| 0:00 | Dark room, phone glow | caption "One sentence." | — |
| 0:03 | Phone, Wispr active | "Room service. Tonight we ship the Volt waitlist page. Block nine to eleven and remind me at eleven." | — |
| 0:08 | Desk | light/flash, ignition, "Evening. Booting Volt.", VS Code, terminal, browser, music | A1–A2 |
| 0:20 | HUD + Mattermost | `mission-volt-waitlist` appears; crew lights up | A3 |
| 0:35 | Phone | mission card; `🗓️ blocked 21:00–23:00` | A7 |
| 0:45 | Mattermost | `!roles` → hands · desk-laptop | A4 |
| 0:55 | Phone | "Show me." → screenshot | A5 |
| 1:05 | Phone | "Make the join button orange and bigger, add confetti." | — |
| 1:10–1:40 | Split | builder works (×4 speed, caption "real time 40 s"); `ok K7Q3` | A6, A8 |
| 1:45 | Phone | new screenshot | — |
| 1:55 | Desk | close lid → second laptop HUD "HANDS TRANSFERRED" | A9 |
| 2:10 | Phone | "Wrap up." → `ok` → diary, goodnight, apps close | A10 |
| 2:30 | HUD | architecture card: "Remove Switch and the room has no body, no memory, no leash." | — |
| 2:40 | Title | "RoomService · built by voice with Wispr Flow · #HowISwitch" | — |
**Fallback:** record each segment separately as soon as it passes (from 19:00 on). If a live segment fails during final recording, use the earlier passing take. Keep `runtime.jsonl` of each take as proof.

---

## 22. README, blog, Wispr (Yash, RS-15)

### 22.1 README headings (exact order)
1. `# RoomService` + pitch + 10-s ignition GIF · 2. `## Watch the demo` · 3. `## What breaks without Switch` (§3.5 table) · 4. `## Architecture` (`docs/architecture.png` + 3 sentences) · 5. `## Try it in 10 minutes` (dry run: Console, `roomservice register`, crew template, pair, `up --dry-run`, say "room service boot volt" in HQ) · 6. `## Full setup` (§9, n8n, Telegram) · 7. `## Talk to it` (what you say → what happens) · 8. `## The hands grammar` (§12.3) · 9. `## What hands will never do` (§17) · 10. `## Built by voice` · 11. `## Tests` · 12. `## Next` (room follows you; borrow a friend's hands; mission template store) · 13. `## Team` (Lakshay Sharma, Yash Goel) · 14. `## License`.

### 22.2 Blog (Best Blog: clarity, accuracy, helps a first-time Switch user)
dev.to post "I gave my room a body with Switch": what Switch is in 3 lines → setup steps with screenshots → writing a protocol agent in 80 lines (connection, ping/pong, addressed messages) → templates run by agents → roles and handoff → 6 gotchas we hit → link repo + video. Tags: `switch`, `ai`, `agents`, `howiswitch`.

### 22.3 Wispr Flow (Code with Wispr)
- Both builders dictate every prompt to Claude Code, room instructions, README, blog, PR descriptions with Wispr Flow from the first minute.
- `VOICE_LOG.md` table: `| time IST | who | where | what (≤ 12 words) |`; ≥ 30 rows by submission (≥ 15 each).
- Demo's first HQ sentence is spoken through Wispr; one 5-s shot shows the Wispr indicator.
- 22:00 IST: each builder screenshots Wispr Flow → Insights → `docs/wispr/lakshay.png`, `docs/wispr/yash.png`.

---

## 23. Phases and timeline (today, IST)

| Phase | Window | Goal | Exit criteria |
|---|---|---|---|
| P0 Foundations | 13:00–13:45 | Contracts frozen; Switch server live; spikes S0–S2 | RS-01 merged; RS-02 merged; S1, S2 pass |
| P1 Core | 13:45–15:30 | Switch client, desk core, templates, seed project | RS-03..RS-06 merged; S3, S4, S6 pass |
| P2 Desk live + HUD | 15:30–17:30 | Ignition + boot + shot on a real machine; HUD live | RS-07, RS-08 merged; A1, A2, A5 pass |
| P3 Crew loop | 17:30–18:45 | Telegram HQ, mission spawn, relay, approvals | RS-09, RS-10 merged; A3–A6, A8 pass |
| P4 Life + handoff | 18:45–20:00 | n8n life, scheduler, wrap/resume, backup | RS-11, RS-12 merged; A7, A9–A11 pass. **Feature freeze 20:00** |
| P5 Hardening | 20:00–20:45 | Security, chaos, runbook ×3 | RS-13, RS-14 merged; A1–A14 pass |
| P6 Ship | 20:45–23:15 | Video, README, blog, submission | RS-15, RS-16 merged; submitted |

**Cut rule at 18:45:** if P3 isn't merged, cut in this order: scout → desk-backup (use explicit release on one machine) → Gmail (calendar only) → Playwright (screen shots) → scheduler. Never cut MUST items (§24 card tags).

---

## 24. Tickets

### 24.1 Board
| ID | Title | Owner | Phase | Est | Depends on | Tier |
|---|---|---|---|---|---|---|
| RS-01 | Foundations and frozen contracts | Lakshay | P0 | 1.0h | — | MUST |
| RS-02 | Switch server, Console, keys, spikes S0–S2 | Yash | P0 | 0.75h | — | MUST |
| RS-03 | Switch client layer, register CLI, fake Switch | Lakshay | P1 | 2.0h | RS-01 | MUST |
| RS-04 | Switch content: instructions, templates, crew + mission import, S4, S6 | Yash | P1 | 1.5h | RS-02, RS-03 | MUST |
| RS-05 | Desk core: grammar, allowlist, approvals, receipts, state | Lakshay | P1 | 1.5h | RS-01 | MUST |
| RS-06 | Seed project, desk.yaml, setup scripts, macOS permissions | Yash | P1 | 1.0h | RS-01 | MUST |
| RS-07 | Desk live: OS adapters, DeskAgent, ignition, pairing, up/doctor/say CLI | Lakshay | P2 | 2.0h | RS-03, RS-05 | MUST |
| RS-08 | Mission Control HUD (server, demo mode, frontend) | Yash | P2 | 2.0h | RS-01 | MUST |
| RS-09 | Telegram HQ, aliases, concierge tuning, S5/S7 capture, A1–A6 | Yash | P3 | 1.25h | RS-04, RS-07 | MUST |
| RS-10 | Relay, builder approval relay, page screenshots | Lakshay | P3 | 1.25h | RS-07 | MUST (relay) / SHOULD (approval relay, Playwright) |
| RS-11 | n8n life workflow, life agent, scheduler | Yash | P4 | 1.25h | RS-03 | SHOULD |
| RS-12 | Roles, wrap/resume, desk-backup handoff, S8 | Lakshay | P4 | 1.25h | RS-07 | MUST (wrap/resume) / SHOULD (backup) |
| RS-13 | Acceptance runbook ×3, bug bash, demo segment takes | Yash | P5 | 0.75h | RS-09..RS-12 | MUST |
| RS-14 | Security tests, chaos checks, doctor completion | Lakshay | P5 | 0.75h | RS-12 | MUST |
| RS-15 | README, architecture image, blog, VOICE_LOG, Wispr shots | Yash | P6 | 1.5h | RS-09 | MUST |
| RS-16 | Final video edit, #HowISwitch post, submission | Lakshay | P6 | 1.5h | RS-13, RS-14 | MUST |
Totals: **Lakshay 11.25h · Yash 10.0h** of build estimate (+ recording time shared). Yash's Switch/Console operation during P3–P5 balances it.

### 24.2 Ticket cards

**RS-01 · Foundations and frozen contracts · Lakshay · P0**
Scope: `pyproject.toml` (deps §6 incl. `pydantic-settings`; `[tool.pytest.ini_options] asyncio_mode="auto"`, markers `live`), `.gitignore` (`.env`, `infra/.env`, `.venv`, `__pycache__`, `*.png` except `docs/` and `tests/fixtures/`), `.env.example` (§11.1), `roomservice/contracts/*` (§8 exactly), `log.py`, `store.py` (atomic JSON writes, chmod 600 for secrets), `bus.py`, `tests/conftest.py`, `.github/*` (§25), `scripts/tickets.sh` (§25.5), `DECISIONS.md`, `VOICE_LOG.md` header, LICENSE MIT. Package skeleton with empty modules for every path in §7.1 so imports resolve.
Accept: `uv sync` ok; `uv run pytest` green (contract model round-trip tests); CI workflows present; `bash scripts/tickets.sh` prints the board.

**RS-02 · Switch server, Console, keys, spikes S0–S2 · Yash · P0**
Scope: §9.1 on the demo machine; decide demo machine per §5.2 (write in `DECISIONS.md`); `.env` filled locally (not committed); Mattermost desktop app; share `SWITCH_URL` form and server version in `DECISIONS.md`. Run S1 with curl; S0 from the other laptop (`curl`). S2 after RS-03 lands (re-run then).
Accept: `/health` 200; registration key created; DECISIONS lines: demo machine, Switch Console + server versions, S0 result.
(Mostly manual; PR contains only DECISIONS.md lines.)

**RS-03 · Switch client layer, register CLI, fake Switch · Lakshay · P1**
Scope: `switch/http.py`, `switch/connection.py`, `switch/rooms.py`, `agents/base.py`, `spikes.py` (S1–S8 commands; S4/S5/S7 print guided manual steps and watch logs), `cli.py` with `register` + `spike`, `tests/contract/fake_switch.py` + connection tests (§20.3 first 5).
Accept: contract tests green; on a real server `roomservice register --agent desk-laptop` and `roomservice spike s2` pass; S3 passes (text + PNG visible in Mattermost HQ once it exists, else any room).

**RS-04 · Switch content: instructions, templates, imports, S4, S6 · Yash · P1**
Scope: `switch/instructions/*.md` (§10.5–10.9 verbatim), both templates (§10.3–10.4), `templates_build.py` + `build-templates` CLI command + unit test; generate `dist/`; on the demo machine: register (`roomservice register`), import crew, Console agent settings (§9.3), save mission template shared, `!assign-agent @concierge` + `!set-alias @desk-laptop @hands` in Mattermost HQ; run S4 (with desk not yet live: check room, crew, brief doc, kickoff text) and S6.
Accept: crew intro posted in `roomservice-hq`; S4 room created correctly (or fallback path verified and "Template path: OFF" set in concierge.md); results in DECISIONS.

**RS-05 · Desk core · Lakshay · P1**
Scope: `desk/grammar.py`, `allowlist.py`, `approvals.py`, `receipts.py`, `state.py`, `voice.py` (queue; calls adapter), unit tests §20.2 for these.
Accept: all those unit tests green; ≥ 40 grammar cases.

**RS-06 · Seed project, desk.yaml, setup scripts, macOS permissions · Yash · P1**
Scope: `demo/volt` (§18.1), `config/desk.example.yaml` (§12.6), `scripts/setup_mac.sh`, `scripts/setup_windows.ps1`; run setup on the demo machine; grant Screen Recording + Automation; create Focus shortcuts; verify `npm run dev -- --port 5173 --strictPort`.
Accept: setup script idempotent (run twice, no errors); `config/desk.yaml` validates with `load_desk_config`; dev server up in < 5 s.

**RS-07 · Desk live · Lakshay · P2**
Scope: `desk/os/{macos,windows,linux,dry}.py` + `get_adapter`, `desk/actions.py` (all verbs §12.3 except relay/backup specifics), `desk/ignition.py`, `agents/desk.py` (wants_unaddressed for ignition + approvals; sets `bus.on_freeze`), pairing (`pair` CLI + verb), `up` (starts DeskAgent; starts the HUD server, LifeAgent and scheduler through guarded imports — if `roomservice.hud.server`, `agents.life` or `scheduler` doesn't define its entry point yet (`run_hud(port)`, `LifeAgent`, `start_scheduler(desk, life)`), log "skipped: not built yet" and continue), `say`, `doctor` (core checks), unit tests for adapters/ignition/queue, contract desk flow test.
Accept: on the demo machine A1, A2, A5 (screen) pass; `@hands status/help/freeze/unfreeze` work; dry-run works on a machine without the apps.

**RS-08 · Mission Control HUD · Yash · P2**
Scope: `hud/server.py` exposing `async def run_hud(port: int) -> None` (uvicorn `Server(Config(app, host="127.0.0.1", port=port)).serve()` in the runtime's event loop, reading `bus` from `roomservice.bus`), `hud/demo.py`, `hud/static/*` (§16), `hud --demo` CLI command; sample screenshot in `tests/fixtures/sample-shot.png`.
Accept: `roomservice hud --demo` shows every event type correctly at 1920×1080 and 1280×720; 60 fps orb on the demo machine; ignition sequence matches §16.3 timings; reconnect pill works; `S` calls `/api/freeze`.

**RS-09 · Telegram HQ, aliases, concierge tuning, S5/S7, A1–A6 · Yash · P3**
Scope: §9.4 fully; pairing on both surfaces; S7; capture a real builder permission request for S5 into `tests/fixtures/permission_request.json`; tune `concierge.md` wording only if A3 fails (PR includes diff + reason); run A1–A6 on the real setup.
Accept: A1–A6 pass from the phone; fixture committed; DECISIONS updated.

**RS-10 · Relay, builder approval relay, page screenshots · Lakshay · P3**
Scope: `relay.py` (§13), approval relay with fixture-based detection, Playwright `shot page` with fallback, unit tests `test_relay.py`.
Accept: A5 (page), A6 mirrors, A8 pass (or S5 fallback flag documented).

**RS-11 · n8n life workflow, life agent, scheduler · Yash · P4**
Scope: `infra/docker-compose.n8n.yml`, `n8n/life.workflow.json` + `n8n/README.md` (credential steps), `agents/life.py` exposing class `LifeAgent(BaseProtocolAgent)`, `scheduler.py` exposing `def start_scheduler(desk, life) -> AsyncIOScheduler`, `--fire <job>` option on `up` (one line in `cli.py`), contract test with respx.
Accept: A7 passes (or Code-tool fallback documented); `roomservice up --fire morning-brief` posts a brief.

**RS-12 · Roles, wrap/resume, desk-backup handoff, S8 · Lakshay · P4**
Scope: §12.8, §15, `agents/backup.py`, `backup` CLI, mission auto-wrap, lease renew task; run S8 with Yash's/Lakshay's second machine.
Accept: A9 (or explicit mode), A10, A11 pass; DECISIONS has S8 timing.

**RS-13 · Acceptance runbook ×3, bug bash, demo takes · Yash · P5**
Scope: run §20.5 three times; file bugs as `RS-13: fix …` PRs or hand to owner; record each demo segment once it passes (raw files in shared drive, not git).
Accept: three clean runs logged in `DECISIONS.md` with timings.

**RS-14 · Security tests, chaos, doctor completion · Lakshay · P5**
Scope: A12–A14, §20.6 chaos checks, remaining doctor checks (§20.7), redaction tests.
Accept: all pass; `roomservice doctor` all ✅ on the demo machine.

**RS-15 · README, architecture image, blog, VOICE_LOG, Wispr · Yash · P6**
Scope: §22 fully; `docs/architecture.png` (export of §5.3 drawn cleanly); ignition GIF (`docs/ignition.gif`, ≤ 8 MB).
Accept: README renders on GitHub with GIF in first screen; blog draft ready; VOICE_LOG ≥ 30 rows.

**RS-16 · Final video, #HowISwitch, submission · Lakshay · P6**
Scope: edit takes to 2:45 per §21 with captions; upload (YouTube unlisted); post #HowISwitch clip on X + LinkedIn; complete §26 checklist; submit; publish blog (Yash's draft).
Accept: submission confirmation screenshot in `docs/`.

---

## 25. Git and pull-request workflow (both builders)

### 25.1 Branching
- `main` is protected: no direct pushes; merge only through PRs that pass CI and have one approval from the other builder (self-merge allowed after 15 min without review during P5–P6 if CI is green).
- One ticket → one branch → one PR (follow-up fixes allowed as extra PRs with the same ticket ID).
- Rebase on `main` before requesting review: `git fetch origin && git rebase origin/main`.

### 25.2 Branch names
`rs-<NN>-<kebab-summary>` — e.g. `rs-07-desk-live`. Follow-ups: `rs-07-fix-<kebab>`.

### 25.3 PR title and body (the ticket tracker)
- **Title format (enforced by CI):** `RS-<NN>: <Ticket title>` — e.g. `RS-07: Desk live — OS adapters, DeskAgent, ignition, pairing, CLI`.
  Follow-up fix: `RS-07: fix <what>`. Spec/docs/chores outside tickets: `RS-00: <what>`.
  Regex: `^RS-\d{2}: .{5,}$`
- **Merge method:** squash merge; the squash commit message = PR title (so `main` history reads as the ticket log).
- `.github/pull_request_template.md`:
```markdown
## Ticket
RS-NN · <title> · Owner: <Lakshay|Yash> · Phase: P<n>

## What changed
- 

## Acceptance (from SPEC §24.2)
- [ ] criterion 1
- [ ] criterion 2

## Tests
- [ ] `uv run ruff check .`
- [ ] `uv run pytest -m "not live"`
- [ ] Live/spike results (paste timings or "n/a")

## Manual steps for the other builder
- none

## Wispr
- [ ] Prompts and this description dictated with Wispr Flow
```

### 25.4 Commits
Inside a branch: `RS-<NN>: <imperative message>` (e.g. `RS-05: add approval TTL`). Small commits are fine; squash merge cleans them.

### 25.5 `scripts/tickets.sh` (board from PR titles)
```bash
#!/usr/bin/env bash
# Prints ticket status from merged/open PR titles. Requires gh CLI logged in.
set -euo pipefail
declare -A OWNER=( [01]=Lakshay [02]=Yash [03]=Lakshay [04]=Yash [05]=Lakshay [06]=Yash [07]=Lakshay [08]=Yash
                   [09]=Yash [10]=Lakshay [11]=Yash [12]=Lakshay [13]=Yash [14]=Lakshay [15]=Yash [16]=Lakshay )
merged=$(gh pr list --state merged --limit 200 --json title -q '.[].title' | grep -oE '^RS-[0-9]{2}' | sort -u || true)
open=$(gh pr list --state open --limit 200 --json title -q '.[].title' | grep -oE '^RS-[0-9]{2}' | sort -u || true)
printf "%-6s %-8s %-8s\n" TICKET OWNER STATUS
for n in $(seq -w 1 16); do
  id="RS-$n"; s="todo"
  grep -qx "$id" <<<"$open" && s="in-PR"
  grep -qx "$id" <<<"$merged" && s="merged"
  printf "%-6s %-8s %-8s\n" "$id" "${OWNER[$n]}" "$s"
done
```
A ticket counts as **merged** when at least one PR titled `RS-NN: …` (not `fix`) is merged; fix PRs don't change status.

### 25.6 CI (`.github/workflows/ci.yml` and `pr-title.yml`)
```yaml
# ci.yml
name: ci
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.12
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -m "not live" -q
```
```yaml
# pr-title.yml
name: pr-title
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]
jobs:
  title:
    runs-on: ubuntu-latest
    steps:
      - env: {TITLE: "${{ github.event.pull_request.title }}"}
        run: |
          echo "$TITLE" | grep -Eq '^RS-[0-9]{2}: .{5,}$' || { echo "PR title must be 'RS-NN: <title>'"; exit 1; }
```

### 25.7 CODEOWNERS
RS-01 fills real GitHub handles (from `gh api user -q .login` on each machine; ask the operator for the other handle):
```
roomservice/contracts/   @<lakshay> @<yash>
roomservice/switch/      @<lakshay>
roomservice/desk/        @<lakshay>
roomservice/agents/desk.py   @<lakshay>
roomservice/agents/backup.py @<lakshay>
roomservice/relay.py     @<lakshay>
roomservice/hud/         @<yash>
roomservice/agents/life.py   @<yash>
roomservice/scheduler.py @<yash>
switch/                  @<yash>
n8n/ infra/ demo/ docs/  @<yash>
SPEC.md DECISIONS.md     @<lakshay> @<yash>
```

### 25.8 Collaboration rules
- Post in your team chat when you open a PR and when you merge (one line: `RS-07 merged`).
- Contracts are frozen after RS-01. Need a change? Open `RS-00: contract change — <what>` and get the other's approval before building on it.
- If blocked on the other person's ticket for > 20 min: code against the contract with a stub and say so in the PR.
- Never force-push `main`. Force-push your own branch only after rebase.

---

## 26. Submission checklist (RS-16)
- [ ] Repo public, MIT, `gitleaks detect` clean
- [ ] `switch/templates/dist/*.yaml` import cleanly on a fresh Console
- [ ] README §22.1 with GIF first; architecture image; "What breaks without Switch"
- [ ] CI green on `main`; test badge in README
- [ ] Clean clone: `uv sync && uv run roomservice up --dry-run` works with only Console running
- [ ] Video ≤ 2:45, captions, YouTube unlisted, linked in README
- [ ] Track 02 selected; Code with Wispr opted in; `docs/wispr/lakshay.png` + `yash.png`; VOICE_LOG ≥ 30 rows
- [ ] Both team members on the submission
- [ ] Blog published and linked
- [ ] #HowISwitch posts on X + LinkedIn, tagging WeMakeDevs and Switch
- [ ] Both starred the Switch repo
- [ ] Submitted by 23:15 IST; confirmation screenshot saved

---

## 27. Risks
| Risk | L | I | Mitigation |
|---|---|---|---|
| Agent-run template refused (addressing/kickoff/validation) | M | H | S4 in P1; concierge fallback path ready (§10.4) |
| Builder approvals can't be relayed | M | M | S5; flag off; desk approvals carry the demo |
| Lease lapse slow | M | M | S8; explicit release mode |
| Claude Code session start latency 10–30 s | H | M | Ignition doesn't wait; HUD fills the gap; video speeds ×4 with caption |
| Busy agent drops message | M | M | Concierge never sends builder two messages in a row; desk queues + acks |
| Second machine can't reach server | M | M | SSH port forward (§5.2) |
| macOS permission prompts block actions | H | M | RS-06 grants Screen Recording + Automation in advance; doctor checks |
| Google OAuth delays | M | L | Code-tool fallback |
| Telegram privacy mode on | L | H | Turn off before adding bot |
| Windows-only machines | L | H | Console Windows is early access; adapters exist; prefer any Mac for the demo |
| Merge conflicts between two Claude Code sessions | M | M | Ownership map §7.2, frozen contracts, small PRs, rebase rule |
| Running out of time | M | H | Cut rule §23; record passing segments early |

---

## Appendix A — Switch reference (verified 7 Nov 2026)

**Registration** `POST /agents` (bearer: registration key). Body: `name` (`^[a-z0-9][a-z0-9._-]*$`), `description`, `connector_type` (free-form), `integration_profile` {`connection_model` ∈ `always_on|session_addressable|auto_session|session_passive`, `message_exchange` bool, `pre_invocation_mediation` [], `post_invocation_mediation` [], `event_reporting` []}; optional `display_name`, `icon_url`, `tools`, `models`, `metadata`, `overwrite`. Response `{id, api_key}` (key shown once). Same name → 409; `overwrite:true` rotates key. Don't use `/agents/register-known`.

**Addressing** `POST /agents/{id}/ops/update_agent_detail` `{"agent_id","addressing": "owner_only|owner_and_owner_agents|anyone"}`. New agents answer owner only.

**WebSocket** `GET /agents/{id}/connection/ws` with `Authorization: Bearer <key>`. Query: `connection_id` (required, reuse), `scope` single|all, `filter` all|addressed, `start_from` head|<seq>, `rooms` (comma ids, takeover), `expected_generation`, `spawn_capable`, `protocol`, `protocol_accepts`, `client`, `client_version`. First frame `connection_state` {connection_id, agent_id, generation, scope, filter, spawn_capable, rooms, cursor, protocol, heartbeat_interval_seconds, server, client}. Server `ping` every 2 s; reply `{"type":"pong","cursor":N}` immediately; 6 s silence → `evicted heartbeat_lapsed`. Domain frame: `{"event":"message","data":{"type","room_id","bridge_id","channel_type","payload",…,"sequence":N},"id":N}`. Control frames: `connection_state`, `gap` {from_sequence, resumed_at, resumed_position, rooms, all_rooms, reason}, `evicted` {code, reason}, `subscription_changed` {rooms, reason}, `room_released` {room_id, session_id}, `ping`, `refused` {status, detail}. Close codes: 1000, 1011, 1012 (restart), 4400 bad params, 4401 auth, 4403 room can't be served, 4409 takeover/protocol/claimed/too many/managed. Eviction codes: `taken_over` (stop), `heartbeat_lapsed`/`no_stream`/`unfenced`/`connection_error` (reconnect), `closed` (read reason). Max 32 connections per agent. Declare rooms on the open URL (later subscribe loses catch-up).

**Events** `message` payload: `addressed, sender, sender_name, message_id, body, timestamp (ms), thread_id, attachments[] (filename, mimetype, size, mxc, msgtype)`. `command`: `command, args, user_id, user_name, thread_id` (never addressed). `room_join`: `member, member_name, timestamp, listening`. Participant ids look like `@switch-<type>-<id>:<server>` — treat as opaque. Markers `com.switch.admin` (Switch's own voice), `com.switch.auto_reply`, `com.switch.attachment_group`.

**Operations** `GET /agents/{id}/ops` → registry; `POST /agents/{id}/ops/{name}` with args unwrapped, header `X-Switch-Connection-Id` binds to a room. Errors 400 (bad/missing/unexpected args — validated by signature), 403, 404, 409 (dead connection). Signatures used here:
`list_rooms(include_archived=False)` · `list_all_rooms(include_archived=False, name_contains=None, limit=100, cursor=None)` · `connect_to_room(room_id, include_general_instructions=True)` · `post_message(body, thread_id=None)` · `send_targeted_message(body, target_names=None, target_roles=None, thread_id=None)` · `read_context(limit=50, since=None, before=None, room_id=None)` · `list_participants()` · `create_room(name, description, agent_names, user_names=None, channel_type=None, bridge_id=None, internal_only=False, admin_mode=False, security_config=None, instructions=None, reference_ids=None, package_ids=None, linked_rooms=None, read_visibility="public", write_visibility="public", group_name=None, roles=None, include_subagents_for=None, join_event_listeners=None, aliases=None, include_owner=False)` · `create_room_document(name, description, instructions, content)` · `update_room_document(document_id, name=None, description=None, instructions=None, content=None)` · `load_internal_documents(ids)` · `list_roles()` · `define_role(name, instructions, exclusive=False)` · `assume_role(role)` · `release_role()` · `link_rooms(source_room_id, target_room_id, label)` · `invite_agent_to_room(room_id, agent_name, include_subagents=False)` · `list_agents(name_contains=None, owner_name=None, known_agent_type=None)` · `list_templates(query=None, kind=None)` · `get_template(template_id)` · `run_template(template_id, inputs=None, agents=None)` · `create_room_from_yaml(yaml, inputs=None)` · `update_agent_detail(agent_id, name=None, description=None, display_name=None, icon_url=None, addressing=None, …)` · `get_room_detail(room_id)` · `update_room(room_id, …, aliases=None)` · `archive_room(room_id)`.

**Non-op HTTP** `POST /agents/{id}/message` {room_id, content} → {ok, event_id} (429 budget, 422 guardrail) · `POST /agents/{id}/rooms/{room_id}/media` multipart `file`|`files`, `caption`, `thread_id` · `GET /agents/{id}/rooms/{room_id}/media?mxc=` · `POST /agents/{id}/typing` {room_id, is_typing} · `POST /agents/{id}/leases/renew` (header connection id) · `GET /health` (public) · `GET /version`.

**Templates** v1 keys: `version, params, agent|agents, room, group/rooms/links, kickoff, form`. Param types: string, number, boolean, enum, agent, bridge, room, user, provider, location, machine, directory; `default` single or chain (`$first`, `$new`); `input` ask|advanced|fixed. Builtins `{$creator}`, `{$creator_email}`, `{$date}`, `{$timestamp}`, `{$agents_dir}`, `{agent}`. Room block: `name, description, instructions, bridge, channel_type, read_visibility, write_visibility, agents, users, roles [{name, instructions, exclusive}], references, packages, docs [{name, description, instructions, content}], aliases`. Agent block: `name, display_name, icon_url, description, instructions, provider, machine, location, directory, model, advanced_config, isolation, auto_mode, auto_approve, can_manage_agents, connections, repo, sources, addressing (owner|owner-agents|anyone), join, allow_existing`. Kickoff run by an agent speaks for that agent; mentioned agents must accept it under their addressing, or nothing is created. Rooms named in `agents:` must exist unless the template creates them.

**Rooms behaviour** Addressing via `@name` or alias (`@name.` addresses nobody). Follow-ups (Console servers: on) start only from a person. `!assign-agent @x` makes a main agent. Approvals: reply exactly `yes`/`no`. One role per agent across all rooms. Telegram: one bot for all agents (name prefix on messages), privacy off before adding, bots can't create groups, nothing public needed.

Sources: docs.switchagents.ai (`llms.txt`, framework, how-switch-works, agent-protocol, agent-connection, agent-events, room-commands, agent-settings, work-in-a-room, telegram, room-templates, host-remotely), github.com/sandbox-quantum/switch (`docs/TEMPLATES.md`, `core/switch_core/bridges/agent/operations/definitions.py`, `core/switch_core/bridges/agent/api/handlers.py`), wemakedevs.org/hackathons/switch (+ rules, resources, schedule).

## Appendix B — Changelog
**v3 (this):** fixed 21 issues found in v2: kickoff addressed an unheld role (now `@desk-laptop`); desk/life absent from HQ (now in crew room + Telegram invites); registration order vs template validation; concierge reacting to `ok CODE` (ignore rules) and desk reading approvals unaddressed; `@hands` alias in HQ rooms; macOS Screen Recording/Automation permissions; `websockets` `additional_headers`; n8n compose/activation/OAuth redirect/timezone; builder–desk–dev-server co-location and machine topology; remote server access + SSH fallback; second-mission auto-wrap; Telegram length limits; HUD agent-state rules made deterministic; frozen contracts for parallel work; ownership map; CI; PR/ticket system; full hackathon + Switch context for a fresh session; exact `build-templates` behaviour; Node/git identity in setup; demo fallback takes; doctor screen-recording check.
**v2:** Life agent, relay, native media, `run_template`, role mechanics, grammar, HUD, voice out, security, tests.
**v1:** concept, research, high-level plan.

## Appendix C — Glossary
**HQ** — the owner's control rooms (`roomservice-hq` on Mattermost, `RoomService HQ` on Telegram). **Mission** — one goal, one room `mission-<slug>`, one active at a time. **hands** — the exclusive role held by a desk agent; the body of the room. **Ignition** — the desk's instant reaction to the owner's wake phrase. **Receipt** — the desk's one-line report of an action. **Relay** — mirroring mission events to HQ. **Pairing** — binding the owner's exact participant ids to the desk. **Demo machine** — the one machine running server, Console agents, runtime, HUD and dev server.
