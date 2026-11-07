#!/usr/bin/env bash
# Start a local Switch server (Docker Compose: Switch API + Mattermost + Gateway) for RoomService.
#
# Why not "Let Switch Console run a server"? That server has no Gateway link in Console 0.40, and the Gateway
# is the only place to create the registration key RoomService needs. This stack has the Gateway on :3000.
#
# Usage: bash scripts/setup_switch_server.sh [--dir DIR] [--version X.Y.Z] [--no-start]
#   --dir      where the stack lives (default: $SWITCH_STACK_DIR or ~/switch-server)
#   --version  Switch server release (default 0.31.0; Switch Console 0.40 needs >= 0.31.0)
#   --no-start write the config only, do not start Docker (used by tests)
# Idempotent: an existing stack keeps its secrets; re-running just starts it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="${SWITCH_STACK_DIR:-$HOME/switch-server}"
VERSION="${SWITCH_VERSION:-0.31.0}"
START=1
# Pinned commit of github.com/sandbox-quantum/switch the compose file and secret generator come from.
# (Their licence does not allow copying the files into this repo, so they are downloaded at setup time.)
REF="${SWITCH_REPO_REF:-195e1208c943f64f9a5f8e75941e3cafaae8d09d}"
RAW="https://raw.githubusercontent.com/sandbox-quantum/switch/$REF"

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --no-start) START=0; shift ;;
    -h|--help) sed -n 2,13p "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

step() { printf '== %s\n' "$1"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1 ($2)" >&2; exit 1; }; }
setvar() { # setvar FILE KEY VALUE (portable in-place edit)
  local f="$1" k="$2" v="$3"
  if grep -q "^${k}=" "$f"; then
    sed -i.bak "s|^${k}=.*|${k}=${v}|" "$f" && rm -f "$f.bak"
  else
    printf '%s=%s\n' "$k" "$v" >> "$f"
  fi
}
getvar() { grep -E "^$2=" "$1" | head -1 | cut -d= -f2- | cut -d'#' -f1 | tr -d ' '; }

need curl "https://curl.se"
need openssl "needed to generate secrets"
if [ "$START" = 1 ]; then
  need docker "install Docker Desktop: https://www.docker.com/products/docker-desktop"
  docker info >/dev/null 2>&1 || { echo "Docker is installed but not running. Open Docker Desktop and re-run." >&2; exit 1; }
  docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required (docker compose)." >&2; exit 1; }
fi

step "Stack folder: $DIR"
mkdir -p "$DIR"
cd "$DIR"
curl -fsSL "$RAW/deploy/local/standalone-docker-compose.yml" -o docker-compose.yml
curl -fsSL "$RAW/deploy/local/generate-env-secrets.sh" -o generate-env-secrets.sh
curl -fsSL "$RAW/.env.example" -o .env.example

if [ ! -f .env ]; then
  step "Generating .env with fresh secrets (kept private, mode 600)"
  cp .env.example .env
  setvar .env SWITCH_VERSION "$VERSION"
  setvar .env FRONTEND_BASE_URL "http://localhost:$(getvar .env GATEWAY_HOST_PORT)"
  # Needed for `!assign-agent` / follow-ups: without it concierge never hears un-mentioned messages.
  setvar .env FEATURE_FLAGS_ENABLED "follow_the_conversation"
  bash generate-env-secrets.sh .env roomservice
  chmod 600 .env
else
  echo ".env already exists, keeping its secrets."
fi

API_PORT="$(getvar .env API_HOST_PORT)"; API_PORT="${API_PORT:-8000}"
GW_PORT="$(getvar .env GATEWAY_HOST_PORT)"; GW_PORT="${GW_PORT:-3000}"
MM_PORT="$(getvar .env MATTERMOST_HOST_PORT)"; MM_PORT="${MM_PORT:-8065}"
SWITCH_URL="http://127.0.0.1:${API_PORT}"

if [ "$START" = 1 ]; then
  step "Starting Switch $VERSION (first run downloads images, a few minutes)"
  docker compose --profile collab --profile gateway up -d
  step "Waiting for $SWITCH_URL/health"
  for _ in $(seq 1 90); do
    [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$SWITCH_URL/health")" = 200 ] && break
    sleep 2
  done
  [ "$(curl -s -o /dev/null -m 2 -w '%{http_code}' "$SWITCH_URL/health")" = 200 ] \
    || { echo "Switch did not become healthy. See: (cd $DIR && docker compose logs switch)" >&2; exit 1; }
fi

step "Writing SWITCH_URL into $ROOT/.env"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
setvar .env SWITCH_URL "$SWITCH_URL"

cat <<TXT

Switch is ready$( [ "$START" = 1 ] || echo " (config only, not started)").

  API (SWITCH_URL)  $SWITCH_URL
  Gateway (admin)   http://127.0.0.1:${GW_PORT}   sign in as $(getvar "$DIR/.env" GATEWAY_ADMIN_EMAIL)
  Mattermost        http://127.0.0.1:${MM_PORT}   user "$(getvar "$DIR/.env" MATTERMOST_USER)", team "$(getvar "$DIR/.env" MATTERMOST_TEAM_NAME)"

Passwords are in $DIR/.env. Copy one to the clipboard without printing it (macOS):
  grep ^GATEWAY_ADMIN_PASSWORD "$DIR/.env" | cut -d= -f2 | pbcopy
  grep ^MATTERMOST_USER_PASSWORD "$DIR/.env" | cut -d= -f2 | pbcopy

Next: docs/SETUP.md, step 3 (create the registration key in the Gateway).
TXT
