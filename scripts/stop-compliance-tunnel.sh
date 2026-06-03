#!/usr/bin/env bash
set -euo pipefail

LOCAL_PORT="${COMPLIANCE_LOCAL_PORT:-8000}"
pid="$(lsof -t -i ":${LOCAL_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"

if [[ -z "$pid" ]]; then
  echo "No tunnel on port ${LOCAL_PORT}"
  exit 0
fi

kill "$pid"
echo "Stopped SSH tunnel (pid ${pid}) on port ${LOCAL_PORT}"
