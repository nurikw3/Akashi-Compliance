#!/usr/bin/env bash
# Open Compliance Workspace via SSH tunnel + auto-login.
#
# Reads ADMIN_USERNAME / ADMIN_PASSWORD from project .env
# Usage: ./scripts/open-compliance.sh
# Stop:  ./scripts/stop-compliance-tunnel.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

SSH_HOST="${COMPLIANCE_SSH_HOST:-185.191.212.72}"
SSH_PORT="${COMPLIANCE_SSH_PORT:-54223}"
SSH_USER="${COMPLIANCE_SSH_USER:-admin1}"
LOCAL_PORT="${COMPLIANCE_LOCAL_PORT:-3001}"
REMOTE_PORT="${COMPLIANCE_REMOTE_PORT:-3001}"

read_env() {
  local key="$1"
  local default="${2:-}"
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "$default"
    return
  fi
  local line
  line="$(grep -E "^${key}=" "$ENV_FILE" | tail -1 || true)"
  if [[ -z "$line" ]]; then
    echo "$default"
    return
  fi
  local value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#\"}"
  value="${value%\"}"
  echo "$value"
}

ADMIN_USERNAME="$(read_env ADMIN_USERNAME "nurikw3")"
ADMIN_PASSWORD="$(read_env ADMIN_PASSWORD "Ak4sh1_Nurik_2026!")"

tunnel_pid() {
  lsof -t -i ":${LOCAL_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

start_tunnel() {
  local pid
  pid="$(tunnel_pid)"
  if [[ -n "$pid" ]]; then
    echo "SSH tunnel already listening on :${LOCAL_PORT} (pid ${pid})"
    return
  fi

  echo "Starting SSH tunnel → ${SSH_USER}@${SSH_HOST}:${SSH_PORT} ..."
  ssh -f -N \
    -p "$SSH_PORT" \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" \
    "${SSH_USER}@${SSH_HOST}"

  sleep 1
  pid="$(tunnel_pid)"
  if [[ -z "$pid" ]]; then
    echo "Failed to start tunnel on port ${LOCAL_PORT}" >&2
    exit 1
  fi
  echo "Tunnel ready (pid ${pid})"
}

build_url() {
  python3 - <<PY
import base64, urllib.parse
user = ${ADMIN_USERNAME@Q}
password = ${ADMIN_PASSWORD@Q}
token = base64.b64encode(f"{user}:{password}".encode()).decode()
print(f"http://127.0.0.1:${LOCAL_PORT}/#auth={urllib.parse.quote(token, safe='')}")
PY
}

open_browser() {
  local url="$1"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    open "$url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url"
  else
    echo "Open in browser: $url"
  fi
}

wait_for_app() {
  local i
  for i in {1..15}; do
    if curl -sf -o /dev/null "http://127.0.0.1:${LOCAL_PORT}/"; then
      return 0
    fi
    sleep 1
  done
  echo "App not responding on http://127.0.0.1:${LOCAL_PORT}/" >&2
  exit 1
}

main() {
  start_tunnel
  wait_for_app
  url="$(build_url)"
  echo "Opening ${url%%#*} (auto-login) ..."
  open_browser "$url"
  echo ""
  echo "Site:  http://127.0.0.1:${LOCAL_PORT}/"
  echo "Stop:  ./scripts/stop-compliance-tunnel.sh"
}

main
