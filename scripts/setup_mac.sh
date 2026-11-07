#!/usr/bin/env bash
# RoomService setup for macOS. Idempotent: safe to run twice.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="$HOME/roomservice-workspace"
VOLT="$WORKSPACE/projects/volt"
fail=0
ok()   { printf '  ✅ %s\n' "$1"; }
bad()  { printf '  ❌ %s\n' "$1"; fail=1; }
warn() { printf '  ⚠️  %s\n' "$1"; }

echo "== Checks"
[ "$(uname -s)" = "Darwin" ] && ok "macOS" || bad "this script is for macOS (use scripts/setup_windows.ps1 on Windows)"
command -v brew >/dev/null 2>&1 && ok "brew" || bad "brew missing: https://brew.sh"
command -v uv >/dev/null 2>&1 && ok "uv" || bad "uv missing: brew install uv"
if command -v node >/dev/null 2>&1; then
  major="$(node -v | sed -E 's/^v([0-9]+).*/\1/')"
  if [ "$major" -ge 20 ]; then ok "node $(node -v)"; else bad "node $(node -v) is older than 20: brew install node"; fi
else
  bad "node missing: brew install node"
fi
command -v npm >/dev/null 2>&1 && ok "npm" || bad "npm missing: brew install node"
if docker info >/dev/null 2>&1; then ok "Docker running"; else bad "Docker is not running: open Docker Desktop"; fi
if command -v code >/dev/null 2>&1; then
  ok "code CLI"
else
  warn "code CLI missing: in VS Code run Cmd+Shift+P, then \"Shell Command: Install 'code' command in PATH\""
fi
if [ "$fail" -ne 0 ]; then
  echo "Fix the ❌ items above and run this script again."
  exit 1
fi

echo "== Workspace"
mkdir -p "$WORKSPACE"/{concierge,scout,projects}
ok "$WORKSPACE"

if [ ! -d "$VOLT" ]; then
  cp -R "$ROOT/demo/volt" "$VOLT"
  ok "copied demo/volt to $VOLT"
else
  ok "$VOLT already exists (left as is)"
fi
( cd "$VOLT" && npm install --no-audit --no-fund >/dev/null )
ok "npm install in volt"

if [ ! -d "$VOLT/.git" ]; then
  (
    cd "$VOLT"
    git init -q -b main
    git config user.name "RoomService"
    git config user.email "roomservice@local"
    printf 'node_modules/\ndist/\n' > .gitignore
    git add -A
    git commit -q -m "Initial commit"
  )
  ok "git init + initial commit in volt"
else
  ok "volt is already a git repo"
fi

echo "== RoomService"
cd "$ROOT"
[ -f config/desk.yaml ] || cp config/desk.example.yaml config/desk.yaml
ok "config/desk.yaml"
[ -f .env ] || cp .env.example .env
ok ".env (fill in SWITCH_URL and SWITCH_REGISTRATION_KEY)"
uv sync >/dev/null
ok "uv sync"
uv run playwright install chromium >/dev/null
ok "playwright chromium"

cat <<'TXT'

== macOS permissions (do these once, by hand)
  1. System Settings > Privacy & Security > Screen Recording:
     enable the terminal app that runs `roomservice` (otherwise screenshots are black or wallpaper only).
  2. Automation: the first time the desk opens a terminal, macOS asks whether
     your terminal app may control "Terminal". Click OK.
  3. Shortcuts app: create two shortcuts, each with the action "Set Focus":
       "RoomService Focus On"  -> Do Not Disturb, turn On
       "RoomService Focus Off" -> Do Not Disturb, turn Off
  4. Quit and reopen the terminal after changing Screen Recording.

Then: uv run roomservice doctor
TXT
