# Try it: ten things to say

Start everything: `bash scripts/demo_up.sh`. The Control Room opens at <http://127.0.0.1:7777>. Say these in the main chat (Telegram or Mattermost). Dictating with Wispr Flow works the same as typing.

| # | Say | What you should see |
|---|---|---|
| 1 | `@computer status` | `✅ status · …` with the task, project folder, dev server and whether the computer is on the job |
| 2 | `Room service, tonight we ship the Volt waitlist page` | Wake-up in the Control Room, a spoken greeting, VS Code and the dev server open, a task room and a plan from the Planner |
| 3 | `show me` | A screenshot of the running page in the chat within about 15 seconds |
| 4 | `make the join button orange and bigger` | The Builder edits `demo/volt` (copy at `~/roomservice-workspace/projects/volt`); ask `show me` again to see it |
| 5 | `@computer open brave` then `@computer url https://news.google.com` | Brave opens and loads the page |
| 6 | `@computer open weather` then `@computer shot screen` | The weather page opens and a screenshot of your screen arrives on your phone |
| 7 | `@computer run git-diff` | The list of files changed in the current project (read-only, no approval needed) |
| 8 | `@computer commit "waitlist v1"` | `⚠️ approval needed · … ok K7Q3`. Nothing happens until you reply `ok K7Q3` |
| 9 | `@computer projects`, then `@computer boot <any folder under ~/cooks>` | Lists your projects, then starts the one you name with no config file |
| 10 | `@computer exec "ls -la"` | An approval request with the exact command; it runs only after `ok CODE` and shows the output |

Also try: `@computer pause` (everything refuses until `@computer unpause`; `S` in the Control Room does the same), `@computer open Steam` (refused: not on the allowlist), `@computer wrap` at the end of the day and `@computer resume volt` the next morning.

**Handoff to a second computer:** copy `config/desk.yaml` to `config/desk.backup.yaml` with `machine_name: backup`, run `ROOMSERVICE_AGENT=desk-backup ROOMSERVICE_DESK_CONFIG=config/desk.backup.yaml HUD_PORT=7778 uv run roomservice backup`, then stop the main desk with Ctrl-C. Within about 15 seconds the chat shows `🫱 the backup computer took over`.

**Only want to see the Control Room?** `uv run roomservice hud --demo` replays a scripted story of every event with no Switch.
