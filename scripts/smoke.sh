#!/usr/bin/env bash
set -euo pipefail
PORT=8084
HOST="${1:-127.0.0.1}"
for ep in health metrics; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://${HOST}:${PORT}/${ep}" || true)
  echo "${ep}: ${code}"
  [ "${code}" = "200" ] || { echo "SMOKE FAIL: ${ep} -> ${code}"; exit 1; }
done
echo "smoke OK on :${PORT}"
