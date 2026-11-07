#!/usr/bin/env bash
# One command from a fresh clone: dependencies, workspace, demo project, Switch server, templates, doctor.
# Usage: bash scripts/bootstrap.sh
# macOS is the primary target. On Windows use scripts/setup_windows.ps1, then docs/SETUP.md.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== 1/4 Machine setup (uv, Node, workspace, demo project, Python deps, Playwright)"
if [ "$(uname -s)" = "Darwin" ]; then
  bash scripts/setup_mac.sh
else
  echo "Not macOS: install uv, Node 20+, Docker and Git yourself, then run: uv sync && uv run playwright install chromium"
  [ -f .env ] || cp .env.example .env
  [ -f config/desk.yaml ] || cp config/desk.example.yaml config/desk.yaml
  uv sync
fi

echo "== 2/4 Switch server (Docker)"
bash scripts/setup_switch_server.sh

echo "== 3/4 Switch templates"
uv run roomservice build-templates

echo "== 4/4 Health check (red lines are expected until the manual steps in docs/SETUP.md are done)"
uv run roomservice doctor || true

cat <<'TXT'

Bootstrap finished. What is left needs a human and takes about 10 minutes:
  1. Create the registration key in the Gateway and put it in .env   (docs/SETUP.md step 3)
  2. uv run roomservice register
  3. Connect Switch Console, import the two templates, set the agents  (steps 5 to 8)
  4. uv run roomservice pair, then start the desk: bash scripts/demo_up.sh
TXT
