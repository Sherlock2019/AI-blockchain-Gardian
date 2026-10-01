#!/bin/sh
# Container entrypoint: run a local Hardhat node and deploy the registry to it.
set -eu

rm -f "$LEDGER_DEPLOYMENT_FILE"
npx hardhat node --hostname 0.0.0.0 &
node_pid=$!

# The deploy script fails until the node accepts connections; retry until it does.
attempt=0
until npx hardhat run scripts/deploy.js --network localhost; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "contract deployment failed" >&2
    exit 1
  fi
  sleep 1
done

wait "$node_pid"
