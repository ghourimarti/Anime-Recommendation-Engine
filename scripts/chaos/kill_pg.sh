#!/usr/bin/env bash
# scripts/chaos/kill_pg.sh — Chaos: simulate Postgres unavailability.
#
# Chaos test for the Postgres-down degradation path.
#
# Mechanism: docker compose stops the postgres service. The readiness probe
# (/ready) starts returning 503; /v1/recommend returns the friendly
# "service temporarily unavailable" path; liveness probe (/health) stays 200
# (the process is up, only its dependency is down). K8s probe semantics in
# docs/architecture.md §3 — this is the local mirror of that flow.
#
# Symmetry: paired with scripts/chaos/restore.sh.
#
# Usage:
#   bash scripts/chaos/kill_pg.sh
#   bash scripts/chaos/kill_pg.sh --dry-run
#   bash scripts/chaos/kill_pg.sh --duration 30

set -euo pipefail

DURATION=15
DRY_RUN=0
BASE_URL="${BASE_URL:-http://localhost:1005}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --duration) DURATION="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

if [[ "$DRY_RUN" -eq 1 ]]; then
    cat <<EOF
[dry-run] would:
  1. docker compose stop postgres
  2. wait 6s (let circuit breakers open + readiness flip)
  3. probe GET  ${BASE_URL}/health     (expect HTTP 200 — liveness OK)
  4. probe GET  ${BASE_URL}/ready      (expect HTTP 503 — readiness fails)
  5. probe POST ${BASE_URL}/v1/recommend (expect HTTP 503 friendly degradation)
  6. wait ${DURATION}s
  7. docker compose start postgres + verify /ready returns 200
EOF
    exit 0
fi

cleanup() {
    echo
    echo "[restore] starting postgres back up…"
    docker compose start postgres >/dev/null 2>&1 || true
    sleep 4
    code=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/ready" || echo "000")
    echo "[restore] /ready returned ${code} (expect 200 within ~10s)"
}
trap cleanup EXIT INT TERM

echo "[chaos] docker compose stop postgres"
docker compose stop postgres >/dev/null

echo "[chaos] waiting 6s for circuit breakers + readiness to flip…"
sleep 6

echo
echo "[probe] GET  ${BASE_URL}/health (expect 200 — liveness):"
curl -s -o /dev/null -w "  HTTP %{http_code}\n" "${BASE_URL}/health" || true

echo "[probe] GET  ${BASE_URL}/ready (expect 503 — readiness):"
curl -s -o /dev/null -w "  HTTP %{http_code}\n" "${BASE_URL}/ready" || true

echo "[probe] POST ${BASE_URL}/v1/recommend (expect 503 friendly):"
curl -s -o /tmp/anime_chaos_response.json -w "  HTTP %{http_code}\n" \
    -X POST "${BASE_URL}/v1/recommend" \
    -H "Authorization: Bearer ${K6_AUTH_TOKEN:-chaos-test}" \
    -H "Content-Type: application/json" \
    -d '{"query":"chaos test — kill PG"}' || true
echo "  body (first 200 chars):"
echo "  $(head -c 200 /tmp/anime_chaos_response.json 2>/dev/null || echo '(no body)')"

cat <<EOF

[verify] WHAT GOOD LOOKS LIKE:
  - /health stays 200 throughout (liveness probe correctly distinguishes
    process-up from dependency-up — K8s should NOT restart this pod)
  - /ready returns 503 within ~6s of postgres stopping (LB pulls the pod)
  - /v1/recommend returns 503 + friendly body
  - Postgres dump on disk is unaffected (this is chaos, not data destruction)

  See docs/hardening/chaos-procedures.md §2 for the full validation checklist.

[hold] chaos held for ${DURATION}s — Ctrl+C to abort + restore early.
EOF
sleep "$DURATION"
