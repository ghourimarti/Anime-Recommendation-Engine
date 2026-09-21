#!/usr/bin/env bash
# scripts/deploy/smoke_k8s.sh — Phase 7 Stage 2 acceptance probe (kind).
#
# Stage 2 asks exactly what Stage 1 asked — does the full e2e flow work? — but
# through kubelet, Services and kube-proxy instead of Docker's bridge. So the
# PROBE is deliberately not reimplemented here: this script owns the thing that
# is genuinely different (getting a route into the cluster) and then delegates
# to scripts/deploy/smoke_local.sh for the actual assertions.
#
# That keeps one definition of "what passing means". Two copies of the probe
# would eventually disagree about the p95 budget or the auth gate, and then the
# two stages would be testing different contracts while appearing to test one.
#
# Port-forward is a single TCP tunnel owned by a child process — it dies when
# this script dies. We start it, wait for it to actually answer, and trap EXIT
# so it is never leaked, including on failure or Ctrl-C.
#
# Usage:
#   bash scripts/deploy/smoke_k8s.sh
#   bash scripts/deploy/smoke_k8s.sh --calls 20 --port 18000
#   bash scripts/deploy/smoke_k8s.sh --help
#
# Env overrides:
#   KIND_CLUSTER   cluster name   (default: anime-local)
#   K8S_NAMESPACE  namespace      (default: anime-local)
#   HELM_RELEASE   release name   (default: anime)
#   K6_AUTH_TOKEN  Clerk dev JWT  — unset means anon-only coverage (exit 2)
#
# Exit codes:
#   0 — all probes green
#   1 — at least one probe failed, or the API never became reachable
#   2 — usage error or auth coverage gap (inherited from smoke_local.sh)

set -euo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
RELEASE="${HELM_RELEASE:-anime}"
CONTEXT="kind-${CLUSTER}"
# 18000, not 8000: a compose stack may already be up on the usual ports, and a
# smoke that silently probes the WRONG stack is worse than one that fails.
PORT=18000
CALLS=10

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)  PORT="$2"; shift 2 ;;
        --calls) CALLS="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

# --- Auth token ------------------------------------------------------
# dev_token.py mints with expires_in_seconds=300 — FIVE minutes. A full cold
# `make deploy-stage2` takes ~10 (cluster recreate, ~4GB image load, ingest), so
# a token exported by the operator before the run is reliably dead by the time
# the smoke runs: every probe 401s with "Signature has expired" and it looks like
# an auth bug rather than a stopwatch. Minting here makes the acceptance
# self-contained instead of dependent on operator timing.
#
# An explicitly exported K6_AUTH_TOKEN still wins, so CI or a hand-run with a
# specific identity keeps working.
if [[ -z "${K6_AUTH_TOKEN:-}" ]] && command -v uv >/dev/null 2>&1 && [[ -f scripts/dev_token.py ]]; then
    echo "  ..    minting a fresh Clerk dev token (5-minute TTL)"
    if minted="$(uv run python scripts/dev_token.py 2>/dev/null | tr -d '\r' | tail -1)" && [[ -n "$minted" ]]; then
        K6_AUTH_TOKEN="$minted"
        export K6_AUTH_TOKEN
        echo "  OK    token minted (${#K6_AUTH_TOKEN} chars)"
    else
        echo "  WARN  could not mint a token — falling back to anon-only coverage" >&2
    fi
fi

PF_PID=""
cleanup() {
    if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" 2>/dev/null; then
        kill "$PF_PID" 2>/dev/null || true
        wait "$PF_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "Stage 2 smoke — cluster '${CLUSTER}', namespace '${NS}', release '${RELEASE}'"
echo

# --- Pre-flight: is there anything to smoke? -------------------------
if ! kubectl config get-contexts "$CONTEXT" >/dev/null 2>&1; then
    echo "  FAIL  no kubectl context '${CONTEXT}' — is the cluster up? (make k8s-up)" >&2
    exit 1
fi
# The Service is named from the CHART name (anime.name), not the release name, and
# listens on 80 while the container listens on 8000. Discovering it rather than
# guessing means a chart rename surfaces as a clear failure here instead of a
# port-forward to a service that does not exist.
API_SVC="$(kubectl --context "$CONTEXT" -n "$NS" get svc -o name 2>/dev/null \
           | sed 's|^service/||' | grep -E -- '-api$' | head -1)"
if [[ -z "$API_SVC" ]]; then
    echo "  FAIL  no *-api service in namespace '${NS}' (make k8s-up)" >&2
    exit 1
fi
echo "  OK    api service: ${API_SVC}"

# --- Route in --------------------------------------------------------
echo "[0/3] port-forward svc/${API_SVC} ${PORT}:80"
kubectl --context "$CONTEXT" -n "$NS" port-forward "svc/${API_SVC}" "${PORT}:80" \
    >/dev/null 2>&1 &
PF_PID=$!

# Do not assume the tunnel is usable the instant kubectl forks. Poll /health
# until it answers or we give up — a fixed `sleep 2` is the classic flake.
BASE="http://localhost:${PORT}"
ready=0
for _ in $(seq 1 30); do
    if ! kill -0 "$PF_PID" 2>/dev/null; then
        echo "  FAIL  port-forward exited early — check 'kubectl -n ${NS} get pods'" >&2
        exit 1
    fi
    if curl -fsS -o /dev/null "${BASE}/health" 2>/dev/null; then
        ready=1
        break
    fi
    sleep 1
done
if (( ! ready )); then
    echo "  FAIL  ${BASE}/health did not answer within 30s" >&2
    exit 1
fi
echo "  OK    tunnel up at ${BASE}"
echo

# --- Delegate the assertions -----------------------------------------
# smoke_local.sh prints its own banner (it predates the stage split and is the
# shared probe for both). Its verdict line is authoritative for the assertions;
# the Stage 2 verdict below is authoritative for this script.
set +e
bash scripts/deploy/smoke_local.sh --base-url "$BASE" --calls "$CALLS"
rc=$?
set -e

echo
case "$rc" in
    0) echo "Stage 2 smoke: PASS" ;;
    2) echo "Stage 2 smoke: INCOMPLETE — auth coverage gap (see warning above)" ;;
    *) echo "Stage 2 smoke: FAIL" ;;
esac
exit "$rc"
