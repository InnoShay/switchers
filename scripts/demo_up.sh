#!/usr/bin/env bash
# One command before recording: Docker + Switch stack + n8n + doctor + the desk (and HUD).
# Usage: bash scripts/demo_up.sh [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK="${SWITCH_STACK_DIR:-$HOME/switch-server}"
cd "$ROOT"

say() { printf '== %s\n' "$1"; }

say "Docker"
if ! docker info >/dev/null 2>&1; then
  open -a Docker
  for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
fi
docker info >/dev/null 2>&1 || { echo "Docker is not running"; exit 1; }

if [ -f "$STACK/docker-compose.yml" ]; then
  say "Switch stack ($STACK)"
  (cd "$STACK" && docker compose --profile collab --profile gateway up -d)
  for _ in $(seq 1 45); do
    [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$(grep -E '^SWITCH_URL=' .env | cut -d= -f2 | cut -d'#' -f1 | tr -d ' ')/health")" = 200 ] && break
    sleep 2
  done
else
  echo "No Switch stack at $STACK (set SWITCH_STACK_DIR); assuming Switch Console runs the server."
fi

if [ -f infra/.env ]; then
  say "n8n"
  docker compose -f infra/docker-compose.n8n.yml --env-file infra/.env up -d
fi

say "doctor"
uv run roomservice doctor || echo "(doctor reported problems above; fix the red lines you care about)"

say "desk + HUD (Ctrl-C to stop)"
exec uv run roomservice up "$@"
