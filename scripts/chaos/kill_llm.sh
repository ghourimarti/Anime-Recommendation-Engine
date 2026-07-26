#!/usr/bin/env bash
# scripts/chaos/kill_llm.sh — Chaos: simulate LLM provider unavailability.
#
# Chaos test for the LLM failure-mode + degradation strategy.
#
# Mechanism: flips LLM_ENABLED=false in .env, force-recreates the api container so
# the env is picked up, then probes /v1/recommend to confirm the degradation path
# fires.
#
# ─── What "good" actually looks like (this was wrong before) ──────────────────
# The script used to print "expecting 503 friendly degradation" and tell the operator
# that 503 was the pass condition. The code has never done that, and shouldn't: with
# the kill switch on, the service serves the POPULAR FALLBACK — HTTP 200, with
# `degraded: true` and a `notice` explaining the reduced quality.
#
# That is the whole point of graceful degradation. The user still gets a usable list
# of anime; they are simply told it isn't personalised right now. A 503 would mean we
# had chosen to fail the request instead of degrading it.
#
# So the script asserted the wrong outcome, and would have "passed" on a genuine
# regression (a real 503 = we broke degradation) while "failing" on correct behaviour.
# A chaos test that checks the wrong invariant is worse than none: it certifies the
# opposite of what you want.
#
# It also probed with `Bearer chaos-test`, which is not a JWT — so every run 401'd at
# the auth layer and never reached the degradation path it claimed to be testing. The
# probe now mints a real token.
#
# Symmetry: paired with scripts/chaos/restore.sh — restore on exit via trap.
#
# Usage:
#   bash scripts/chaos/kill_llm.sh                 # full chaos, restore at end
#   bash scripts/chaos/kill_llm.sh --dry-run       # plan only, no mutation
#   bash scripts/chaos/kill_llm.sh --duration 30   # hold chaos for 30s

set -euo pipefail

DURATION=15
DRY_RUN=0
BASE_URL="${BASE_URL:-http://localhost:1005}"
# The API warms the cross-encoder before readiness flips green, so it takes ~20-25s to
# come up. The old fixed `sleep 8` raced that: the probe usually hit a still-booting
# container and reported a connection error as if it were the chaos result.
READY_TIMEOUT=90

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --duration) DURATION="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] would:"
    echo "  1. cp .env .env.chaos-backup"
    echo "  2. flip LLM_ENABLED=false in .env"
    echo "  3. docker compose up -d --no-deps --force-recreate api"
    echo "  4. poll ${BASE_URL}/ready until healthy (up to ${READY_TIMEOUT}s)"
    echo "  5. probe POST ${BASE_URL}/v1/recommend with a REAL token"
    echo "     expect: HTTP 200, degraded=true, non-empty recommendations (popular fallback)"
    echo "  6. restore .env + force-recreate api"
    exit 0
fi

if [[ ! -f .env ]]; then
    echo "error: .env not found at repo root — create it before running chaos" >&2
    exit 2
fi

cleanup() {
    if [[ -f .env.chaos-backup ]]; then
        echo "[restore] reverting .env + force-recreating api…"
        mv -f .env.chaos-backup .env
        docker compose up -d --no-deps --force-recreate api >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

echo "[chaos] capturing .env → .env.chaos-backup"
cp .env .env.chaos-backup

echo "[chaos] flipping LLM_ENABLED=false in .env"
if grep -q '^LLM_ENABLED=' .env; then
    sed -i.bak 's/^LLM_ENABLED=.*/LLM_ENABLED=false/' .env
    rm -f .env.bak
else
    echo "LLM_ENABLED=false" >> .env
fi

echo "[chaos] force-recreating api container (picks up new env)"
docker compose up -d --no-deps --force-recreate api >/dev/null

# Wait for READINESS, don't guess at it. Readiness only flips green once the reranker
# model is resident, so a fixed sleep either races the boot or wastes time.
echo "[chaos] waiting for api readiness (up to ${READY_TIMEOUT}s)…"
deadline=$(( $(date +%s) + READY_TIMEOUT ))
until curl -sf "${BASE_URL}/ready" >/dev/null 2>&1; do
    if [[ $(date +%s) -ge $deadline ]]; then
        echo "error: api did not become ready within ${READY_TIMEOUT}s" >&2
        exit 1
    fi
    sleep 2
done
echo "[chaos] api ready."

# Auth fails closed by design — there is no bypass. Without a real token the probe
# just 401s and tests nothing, which is exactly what the old script did.
TOKEN="${K6_AUTH_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
    echo "[chaos] minting a dev token (K6_AUTH_TOKEN not set)…"
    TOKEN="$(uv run python scripts/dev_token.py)" || {
        echo "error: could not mint a token; set K6_AUTH_TOKEN and retry" >&2
        exit 1
    }
fi

echo
echo "[probe] POST ${BASE_URL}/v1/recommend (expecting 200 + degraded=true):"
STATUS=$(curl -s -o /tmp/anime_chaos_response.json -w "%{http_code}" \
    -X POST "${BASE_URL}/v1/recommend" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"query":"chaos test - LLM kill switch"}' || true)
echo "[probe] HTTP ${STATUS}"
echo "[probe] response body (first 300 chars):"
head -c 300 /tmp/anime_chaos_response.json 2>/dev/null || echo "(no body)"
echo

# Assert the invariant instead of asking a human to squint at it.
PASS=1
[[ "$STATUS" == "200" ]] || { echo "[verify] FAIL: expected HTTP 200, got ${STATUS}"; PASS=0; }
if ! grep -q '"degraded": *true' /tmp/anime_chaos_response.json 2>/dev/null; then
    echo "[verify] FAIL: response is not marked degraded=true"
    PASS=0
fi
if grep -q '"recommendations": *\[\]' /tmp/anime_chaos_response.json 2>/dev/null; then
    echo "[verify] FAIL: degraded response returned NO recommendations —"
    echo "               the popular fallback should still serve a usable list"
    PASS=0
fi

if [[ "$PASS" -eq 1 ]]; then
    echo "[verify] PASS: 200 + degraded=true + non-empty popular fallback"
else
    echo "[verify] FAILED — degradation did not behave as designed"
fi

cat <<EOF

[verify] WHAT GOOD LOOKS LIKE:
  - HTTP status: 200 (NOT 503 — we DEGRADE the request, we do not fail it)
  - body has  degraded: true  and a user-facing  notice
  - recommendations is NON-EMPTY: the popular fallback still serves a usable list
  - Langfuse shows ZERO LLM calls in the chaos window (the switch really is off)
  - cost for the window is \$0 (that is the point of a kill switch)

  A 503 here would be a REGRESSION, not a pass: it would mean we chose to fail the
  request instead of degrading it.

  See docs/hardening/chaos-procedures.md §1a for the full validation checklist.

[hold] chaos held for ${DURATION}s — Ctrl+C to abort + restore early.
EOF
sleep "$DURATION"

# trap cleanup() fires on exit and restores.
[[ "$PASS" -eq 1 ]] || exit 1
