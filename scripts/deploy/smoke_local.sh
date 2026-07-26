#!/usr/bin/env bash
# scripts/deploy/smoke_local.sh — deployment smoke probe.
#
# Hits /health, /ready, and (when K6_AUTH_TOKEN present) /v1/recommend
# sequentially N times. Reports per-endpoint OK/FAIL and a p50/p95 sample
# for /v1/recommend.
#
# This is the deployment-stage acceptance probe — independent of k6, runs
# anywhere with curl. For a larger-N percentile validation, follow up with
# `make load-smoke` (k6, 1 RPS / 60s).
#
# Gate: hybrid auth coverage.
#   - K6_AUTH_TOKEN unset → anon probes only; exit 2 + clear warning
#   - K6_AUTH_TOKEN set   → full e2e probe; pass/fail on the auth path
#
# Usage:
#   bash scripts/deploy/smoke_local.sh
#   bash scripts/deploy/smoke_local.sh --base-url http://localhost:1005 --calls 10
#   bash scripts/deploy/smoke_local.sh --help
#
# Exit codes:
#   0 — all probes green
#   1 — at least one probe failed (smoke FAIL)
#   2 — usage error or auth coverage gap (warned, not run)

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:1005}"
CALLS=10

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-url) BASE_URL="$2"; shift 2 ;;
        --calls) CALLS="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

# ─── Helpers ──────────────────────────────────────────────────────────
probe_status() {
    # $1 method, $2 url, $3 expected-status, [$4 extra-curl-args]
    local method="$1" url="$2" expected="$3"; shift 3
    local actual
    # curl's -w "%{http_code}" prints "000" on connection failure on its
    # own; no need for `|| echo "000"` (that's the double-print bug).
    actual=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" "$@" || true)
    actual="${actual:-000}"
    if [[ "$actual" == "$expected" ]]; then
        echo "  PASS  ${method} ${url} → ${actual}"
        return 0
    fi
    echo "  FAIL  ${method} ${url} → ${actual} (expected ${expected})"
    return 1
}

ms_now() { date +%s%3N; }

# ─── Stage 1.1: liveness ─────────────────────────────────────────────
FAILED=0
echo "Stage 1 smoke against ${BASE_URL}"
echo
echo "[1/3] liveness probes (anon):"
probe_status GET "${BASE_URL}/health" 200 || FAILED=1
probe_status GET "${BASE_URL}/ready"  200 || FAILED=1

# ─── Stage 1.2: auth coverage (hybrid) ───────────────────────────────
echo
echo "[2/3] auth coverage:"
if [[ -z "${K6_AUTH_TOKEN:-}" ]]; then
    cat <<EOF
  WARN  K6_AUTH_TOKEN not set — auth-path probes SKIPPED.
        Stage 1 acceptance requires the e2e auth flow to be exercised.
        Mint a Clerk dev JWT (tests/load/README.md §2) and re-run.
        Exiting 2 to flag the coverage gap.
EOF
    if [[ "$FAILED" -eq 0 ]]; then
        exit 2
    fi
    # If liveness already failed, that's the primary signal.
    exit 1
fi
echo "  OK    K6_AUTH_TOKEN present — running /v1/recommend probes"

# ─── Stage 1.3: /v1/recommend N times, p50/p95 over the sample ────────
echo
echo "[3/3] /v1/recommend × ${CALLS} (sample p50/p95):"
TIMINGS=()
for i in $(seq 1 "$CALLS"); do
    t0=$(ms_now)
    status=$(curl -s -o /tmp/anime_smoke_response.json -w "%{http_code}" \
        -X POST "${BASE_URL}/v1/recommend" \
        -H "Authorization: Bearer ${K6_AUTH_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"query\":\"stage1 smoke ${i}\"}" || true)
    status="${status:-000}"
    t1=$(ms_now)
    elapsed=$(( t1 - t0 ))
    TIMINGS+=("$elapsed")
    if [[ "$status" == "200" ]]; then
        echo "  PASS  call ${i}: ${status} in ${elapsed}ms"
    else
        echo "  FAIL  call ${i}: ${status} in ${elapsed}ms"
        FAILED=1
    fi
done

# Sort + percentile (bash-only, no jq/python required).
IFS=$'\n' SORTED=($(sort -n <<<"${TIMINGS[*]}")); unset IFS
n=${#SORTED[@]}
p50_idx=$(( n / 2 ))
p95_idx=$(( (n * 95 + 99) / 100 - 1 ))
[[ "$p95_idx" -lt 0 ]] && p95_idx=0
[[ "$p95_idx" -ge "$n" ]] && p95_idx=$(( n - 1 ))

echo
echo "[summary]"
echo "  /v1/recommend p50 ≈ ${SORTED[$p50_idx]}ms"
echo "  /v1/recommend p95 ≈ ${SORTED[$p95_idx]}ms  (N=${n})"
echo "  NFR: full-response p95 < 8000ms (warm cache);"
echo "               first call after cold start will be higher (corpus + reranker load)."

if [[ "$FAILED" -ne 0 ]]; then
    echo
    echo "Stage 1 smoke: FAIL"
    exit 1
fi
echo
echo "Stage 1 smoke: PASS"
