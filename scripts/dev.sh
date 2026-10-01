#!/usr/bin/env bash
# Starts the whole stack locally: Hardhat node, contract deployment, API, dashboard.
#
#   scripts/dev.sh          real local chain (default)
#   scripts/dev.sh --lite   no chain; the ledger is simulated in the backend process
#
# Ctrl-C stops everything.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

mode="hardhat"
[[ "${1:-}" == "--lite" ]] && mode="memory"

if [[ ! -x backend/.venv/bin/uvicorn || ! -d frontend/node_modules || ! -d blockchain/node_modules ]]; then
  echo "Dependencies are missing. Run: make install" >&2
  exit 1
fi

[[ -f .env ]] && set -a && source .env && set +a

pids=()
# npm and npx start the real server as a child and do not pass signals on, so
# each service is stopped as a whole tree, children first.
kill_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill "$1" 2>/dev/null || true
}
cleanup() {
  trap - EXIT INT TERM
  echo
  echo "Stopping…"
  for pid in "${pids[@]}"; do kill_tree "$pid"; done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

mkdir -p .run

# The local chain starts empty every time, so the database does too. Otherwise
# yesterday's receipts would point at records the new chain has never seen.
rm -f backend/trustchain.db

if [[ "$mode" == "hardhat" ]]; then
  echo "[1/4] Starting local Hardhat chain on :8545"
  (cd blockchain && exec npx hardhat node --hostname 127.0.0.1) >.run/chain.log 2>&1 &
  pids+=($!)
  scripts/wait-for-rpc.sh http://127.0.0.1:8545

  echo "[2/4] Deploying TrustChainRegistry and registering the agent"
  (cd blockchain && npx hardhat run scripts/deploy.js --network localhost) | sed 's/^/      /'
else
  echo "[1/4] Skipping the chain (--lite): the ledger is SIMULATED in the backend"
  echo "[2/4] Nothing to deploy"
fi

echo "[3/4] Starting API on :8000"
(
  cd backend
  LEDGER_MODE="$mode" exec .venv/bin/uvicorn app.main:app_factory --factory --host 127.0.0.1 --port 8000
) >.run/backend.log 2>&1 &
pids+=($!)

web_port="${WEB_PORT:-5173}"
public_url="$(scripts/public-url.sh "$web_port")"
# Let the dev server answer to this machine's public hostname as well as localhost.
public_host="${public_url#http://}"
export ALLOWED_HOSTS="${ALLOWED_HOSTS:-${public_host%%:*}}"

echo "[4/4] Starting dashboard on :$web_port"
(cd frontend && exec npm run dev -- --port "$web_port" --strictPort) >.run/frontend.log 2>&1 &
pids+=($!)

for _ in $(seq 60); do
  curl -sf http://127.0.0.1:8000/api/health >/dev/null && break
  sleep 1
done

cat <<EOF

  TrustChain AI is running.

    Dashboard   $public_url
    API docs    http://localhost:8000/docs   (this machine only)
    Ledger      $([[ "$mode" == "hardhat" ]] && echo "Hardhat local chain, http://127.0.0.1:8545" || echo "simulated (in-memory)")
    Logs        .run/backend.log  .run/chain.log  .run/frontend.log

  Ctrl-C to stop.
EOF

wait
