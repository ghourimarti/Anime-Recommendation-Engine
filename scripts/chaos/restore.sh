#!/usr/bin/env bash
# scripts/chaos/restore.sh — Idempotent restore for any chaos scenario.
#
# Safe to run BEFORE any chaos (no-op), DURING (cleanup), or
# AFTER (verify). The point is: never wonder what state the local stack
# is in — run `make chaos-restore`, it converges to "everything healthy."
#
# Actions (each is idempotent + best-effort):
#   1. Restore .env from .env.chaos-backup if present
#   2. Ensure postgres + redis + api are all running
#   3. Reconnect api to the compose network if disconnected
#   4. Probe /ready until 200 or 30s timeout
#
# Usage:
#   bash scripts/chaos/restore.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:1005}"
cd "$(dirname "$0")/../.."

echo "[restore] step 1/4 — restore .env if a chaos backup exists"
if [[ -f .env.chaos-backup ]]; then
    mv -f .env.chaos-backup .env
    echo "  .env restored from .env.chaos-backup"
else
    echo "  no .env.chaos-backup found — skipping"
fi

echo "[restore] step 2/4 — ensure core services are up"
docker compose up -d --no-deps postgres redis api >/dev/null 2>&1 || \
    echo "  docker compose up returned non-zero — continuing"

echo "[restore] step 3/4 — reconnect api to compose network if disconnected"
PROJECT="$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
NETWORK="${PROJECT}_default"
API_CONTAINER="$(docker compose ps -q api 2>/dev/null || true)"
if [[ -n "$API_CONTAINER" ]]; then
    docker network connect "${NETWORK}" "${API_CONTAINER}" 2>/dev/null || \
        echo "  (api already connected — that's fine)"
else
    echo "  api container not found — try: docker compose up -d api"
fi

echo "[restore] step 4/4 — wait for /ready (up to 30s)"
deadline=$(( $(date +%s) + 30 ))
while [[ $(date +%s) -lt $deadline ]]; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/ready" || echo "000")
    if [[ "$code" == "200" ]]; then
        echo "  /ready returned 200 — stack healthy."
        exit 0
    fi
    sleep 2
done

echo "  /ready did NOT return 200 within 30s — check 'docker compose ps' + logs."
exit 1
