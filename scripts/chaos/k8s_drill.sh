#!/usr/bin/env bash
# scripts/chaos/k8s_drill.sh — in-cluster failure drills, measured under load.
#
# WHY ONE SCRIPT AND NOT THREE
# ----------------------------
# The compose drills (kill_llm / kill_pg / net_partition) are separate scripts
# because they are genuinely unrelated disruptions with nothing shared. These
# three share ~80% of their body — start the probe, disrupt, wait for recovery,
# read the probe, decide a verdict. Triplicating that harness would mean three
# copies of the pass criteria, which eventually disagree.
#
# WHAT MAKES THESE DRILLS AND NOT SMOKE TESTS
# -------------------------------------------
# A check that runs AFTER recovery only proves the system came back. The question
# worth asking is whether requests failed WHILE it was broken. k8s_probe_loop.sh
# runs throughout, inside the cluster, so each drill reports continuity rather
# than just eventual recovery.
#
# Usage:
#   bash scripts/chaos/k8s_drill.sh pod-kill
#   bash scripts/chaos/k8s_drill.sh rollout-restart
#   bash scripts/chaos/k8s_drill.sh node-drain
#   bash scripts/chaos/k8s_drill.sh --help
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace     (default: anime-local)
#   DRAIN_TOLERANCE max consecutive failures tolerated by node-drain (default: 0)
#
# Exit codes:
#   0 — drill passed its availability criterion
#   1 — drill failed (requests dropped beyond tolerance, or no recovery)
#   2 — usage error / cluster not reachable

set -uo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"
PROBE="scripts/chaos/k8s_probe_loop.sh"
SETTLE=6          # seconds of baseline before and after the disruption

cd "$(dirname "$0")/../.."
K() { kubectl --context "$CONTEXT" -n "$NS" "$@"; }

DRILL="${1:-}"
case "$DRILL" in
    pod-kill|rollout-restart|node-drain) ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "usage: $0 {pod-kill|rollout-restart|node-drain}" >&2; exit 2 ;;
esac

kubectl config get-contexts "$CONTEXT" >/dev/null 2>&1 \
    || { echo "no kubectl context '${CONTEXT}' — is the cluster up? (make k8s-up)" >&2; exit 2; }

API_DEPLOY="$(K get deploy -o name 2>/dev/null | sed 's|^deployment.apps/||' | grep -E -- '-api$' | head -1)"
[[ -n "$API_DEPLOY" ]] || { echo "no *-api deployment in ${NS}" >&2; exit 2; }

DRAINED_NODE=""
cleanup() {
    # A drill that leaves a node cordoned has silently shrunk the cluster, and the
    # next confusing scheduling failure is hours away from this script. Uncordon
    # unconditionally, including on failure or Ctrl-C.
    if [[ -n "$DRAINED_NODE" ]]; then
        kubectl --context "$CONTEXT" uncordon "$DRAINED_NODE" >/dev/null 2>&1 \
            && echo "  [cleanup] uncordoned ${DRAINED_NODE}"
    fi
    bash "$PROBE" stop >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

echo "=== drill: ${DRILL} ==="
echo "[1/4] starting in-cluster availability probe"
bash "$PROBE" start || exit 2
sleep "$SETTLE"

echo
echo "[2/4] baseline before disruption"
bash "$PROBE" report

echo
echo "[3/4] disruption"
case "$DRILL" in
  pod-kill)
    VICTIM="$(K get pods -l component=api -o name 2>/dev/null | head -1 | sed 's|^pod/||')"
    [[ -n "$VICTIM" ]] || { echo "  no api pod to kill" >&2; exit 2; }
    echo "  deleting pod ${VICTIM}"
    K delete pod "$VICTIM" --wait=false >/dev/null
    K rollout status "deploy/${API_DEPLOY}" --timeout=300s
    ;;
  rollout-restart)
    echo "  kubectl rollout restart deploy/${API_DEPLOY}"
    K rollout restart "deploy/${API_DEPLOY}" >/dev/null
    K rollout status "deploy/${API_DEPLOY}" --timeout=300s
    ;;
  node-drain)
    # Drain a worker that actually hosts an api pod, otherwise the drill drains an
    # empty node and proves nothing while looking green.
    DRAINED_NODE="$(K get pods -l component=api -o jsonpath='{.items[0].spec.nodeName}' 2>/dev/null)"
    [[ -n "$DRAINED_NODE" ]] || { echo "  could not find a node hosting an api pod" >&2; exit 2; }
    echo "  draining ${DRAINED_NODE} (hosts an api pod)"
    # --ignore-daemonsets: DaemonSet pods are recreated by their controller and
    #   cannot be evicted; without this, drain refuses outright.
    # --delete-emptydir-data: our data tier uses emptyDir/PVCs; drain refuses to
    #   evict pods with local data unless told the loss is acceptable.
    kubectl --context "$CONTEXT" drain "$DRAINED_NODE" \
        --ignore-daemonsets --delete-emptydir-data --force --timeout=180s || true
    K rollout status "deploy/${API_DEPLOY}" --timeout=300s
    ;;
esac

sleep "$SETTLE"

echo
echo "[4/4] result"
bash "$PROBE" report
read -r TOTAL OK FAIL GAP < /tmp/anime_probe_stats

TOLERANCE=0
if [[ "$DRILL" == "node-drain" ]]; then
    # Documented tolerance, not a free pass: with no PodDisruptionBudget the
    # eviction is unconstrained, so a gap here is the DEFECT being demonstrated
    # rather than the drill misbehaving. Set to 0 once a PDB exists.
    TOLERANCE="${DRAIN_TOLERANCE:-0}"
fi

echo
if [[ "$TOTAL" -lt 10 ]]; then
    echo "${DRILL}: FAIL — only ${TOTAL} samples; the probe was not measuring"
    exit 1
fi
if [[ "$FAIL" -le "$TOLERANCE" ]]; then
    echo "${DRILL}: PASS — ${OK}/${TOTAL} requests served, ${FAIL} failed (tolerance ${TOLERANCE})"
    exit 0
fi
echo "${DRILL}: FAIL — ${FAIL}/${TOTAL} requests dropped, longest outage ${GAP} consecutive"
echo "  Service continuity broke during the disruption; recovery alone is not the bar."
exit 1
