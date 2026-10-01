#!/usr/bin/env bash
# TrustChain AI launcher.
#
#   ./start.sh         start (Docker if available, otherwise local processes)
#   ./start.sh stop    stop
#
# Set WEB_PORT to change the web UI port (default 5173), e.g. WEB_PORT=80 ./start.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export WEB_PORT="${WEB_PORT:-5173}"

have_docker() { docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; }

if [[ "${1:-}" == "stop" ]]; then
  have_docker && docker compose down -v
  pkill -f "[s]cripts/dev.sh" 2>/dev/null || true
  echo "Stopped."
  exit 0
fi

if have_docker; then
  docker compose up --build -d
  echo
  echo "TrustChain AI is running: $(scripts/public-url.sh "$WEB_PORT")"
  echo "Stop with: ./start.sh stop"
else
  echo "Docker not available; starting local processes (Ctrl-C to stop)."
  [[ -x backend/.venv/bin/uvicorn && -d frontend/node_modules && -d blockchain/node_modules ]] || make install
  exec scripts/dev.sh
fi
