#!/usr/bin/env bash
# Prints the URL of the web UI as seen from outside this machine.
# On AWS EC2 that is the instance's public address (read from instance
# metadata, IMDSv2). Anywhere else it falls back to localhost.
set -uo pipefail

port="${1:-${WEB_PORT:-5173}}"
metadata="http://169.254.169.254/latest"

token="$(curl -sf -m 1 -X PUT "$metadata/api/token" \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null || true)"
host=""
if [[ -n "$token" ]]; then
  for key in public-hostname public-ipv4; do
    host="$(curl -sf -m 1 -H "X-aws-ec2-metadata-token: $token" "$metadata/meta-data/$key" 2>/dev/null || true)"
    [[ -n "$host" ]] && break
  done
fi

suffix=""
[[ "$port" != "80" ]] && suffix=":$port"
echo "http://${host:-localhost}${suffix}"
