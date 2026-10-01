#!/usr/bin/env bash
# Waits until a JSON-RPC endpoint answers eth_chainId, then exits 0.
set -euo pipefail

url="${1:-http://127.0.0.1:8545}"
attempts="${2:-60}"

for _ in $(seq "$attempts"); do
  if curl -sf -X POST -H 'content-type: application/json' \
    --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' "$url" >/dev/null; then
    exit 0
  fi
  sleep 1
done

echo "JSON-RPC endpoint $url did not come up" >&2
exit 1
