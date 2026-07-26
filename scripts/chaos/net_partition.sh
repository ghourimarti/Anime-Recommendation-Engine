#!/usr/bin/env bash
# scripts/chaos/net_partition.sh — Chaos: partition api from redis.
#
# Chaos test for cache-layer graceful degradation.
#
# Mechanism: docker network disconnect drops the api container from the
# compose network of the redis container. Exercises:
#   - Cache layer degrades to "no cache" (correctness preserved, cost degrades)
#   - Circuit breakers around Redis open after N consecutive timeouts
#   - /v1/recommend still returns 200 because Redis is non-critical
#
# This is the cleanest "graceful degradation" chaos — proves the claim
# that Redis-down means "cost degrades, correctness intact."
#
# Symmetry: paired with scripts/chaos/restore.sh.
#
# Usage:
#   bash scripts/chaos/net_partition.sh
#   bash scripts/chaos/net_partition.sh --dry-run
#   bash scripts/chaos/net_partition.sh --target redis|llm   # default redis

set -euo pipefail

DURATION=15
DRY_RUN=0
TARGET="redis"
BASE_URL="${BASE_URL:-http://localhost:1005}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --duration) DURATION="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

# Discover the compose network for the target service.
PROJECT="$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
NETWORK="${PROJECT}_default"
TARGET_CONTAINER="$(docker compose ps -q "$TARGET" 2>/dev/null || true)"
API_CONTAINER="$(docker compose ps -q api 2>/dev/null || true)"

if [[ "$DRY_RUN" -eq 1 ]]; then
    cat <<EOF
[dry-run] would:
  1. docker network disconnect ${NETWORK} ${API_CONTAINER:-<api-container>}
     (api → ${TARGET} partition simulated by removing api from the shared net)
  2. wait 5s (let breakers open)
  3. probe POST ${BASE_URL}/v1/recommend
     - if --target redis: expect HTTP 200 (cache fallback ok)
     - if --target llm:   expect HTTP 503 (LLM has no in-process fallback)
  4. wait ${DURATION}s
  5. docker network connect ${NETWORK} ${API_CONTAINER:-<api-container>}
EOF
    exit 0
fi

if [[ -z "$API_CONTAINER" ]]; then
    echo "error: api container not found — is 'docker compose up' running?" >&2
    exit 2
fi
if [[ -z "$TARGET_CONTAINER" ]]; then
    echo "error: ${TARGET} container not found" >&2
    exit 2
fi

cleanup() {
    echo
    echo "[restore] reconnecting api to ${NETWORK}…"
    docker network connect "${NETWORK}" "${API_CONTAINER}" 2>/dev/null || true
    sleep 3
    code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/ready" || echo "000")
    echo "[restore] /ready returned ${code} (expect 200)"
}
trap cleanup EXIT INT TERM

echo "[chaos] docker network disconnect ${NETWORK} ${API_CONTAINER:0:12} (target: ${TARGET})"
docker network disconnect "${NETWORK}" "${API_CONTAINER}" >/dev/null

echo "[chaos] waiting 5s for circuit breakers to open…"
sleep 5

echo
echo "[probe] POST ${BASE_URL}/v1/recommend:"
if [[ "$TARGET" == "redis" ]]; then
    EXPECT="200 (cache miss; correctness preserved)"
else
    EXPECT="503 friendly (LLM has no in-process fallback when partitioned)"
fi
echo "       expect: ${EXPECT}"
curl -s -o /tmp/anime_chaos_response.json -w "  HTTP %{http_code}\n" \
    -X POST "${BASE_URL}/v1/recommend" \
    -H "Authorization: Bearer ${K6_AUTH_TOKEN:-chaos-test}" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"chaos test — partition ${TARGET}\"}" || true
echo "  body (first 200 chars): $(head -c 200 /tmp/anime_chaos_response.json 2>/dev/null || echo '(no body)')"

cat <<EOF

[verify] WHAT GOOD LOOKS LIKE (--target ${TARGET}):
  - if redis: 200 returned (cache layer correctly degraded); next request
    after partition starts hitting Redis fresh on restore
  - if llm: 503 friendly returned within ~10s (no infinite hang)
  - resilience.py logs show circuit_breaker.open events for ${TARGET}

  See docs/hardening/chaos-procedures.md §3 for the full checklist.

[hold] chaos held for ${DURATION}s — Ctrl+C to abort + restore early.
EOF
sleep "$DURATION"
