#!/usr/bin/env bash
# scripts/deploy/down_local_k8s.sh — Phase 7 Stage 2 teardown.
#
# Default: delete the kind cluster entirely (full cold reset — the honest
# starting point for an acceptance run).
# --soft:  helm uninstall + namespace delete, cluster kept. Fast iteration
#          while debugging chart changes; skips the ~60s cluster create and
#          the image reload.
#
# Idempotent by design: exits 0 when there is nothing to tear down. That is
# what lets up_local_k8s.sh call it as a pre-step without guarding.
#
# Usage:
#   bash scripts/deploy/down_local_k8s.sh
#   bash scripts/deploy/down_local_k8s.sh --soft
#   bash scripts/deploy/down_local_k8s.sh --help
#
# Env overrides:
#   KIND_CLUSTER   cluster name      (default: anime-local)
#   K8S_NAMESPACE  namespace         (default: anime-local)
#   HELM_RELEASE   release name      (default: anime)
#
# Exit codes:
#   0 — teardown complete (including "nothing to tear down")
#   2 — usage error

set -euo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NAMESPACE="${K8S_NAMESPACE:-anime-local}"
RELEASE="${HELM_RELEASE:-anime}"
CONTEXT="kind-${CLUSTER}"
SOFT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --soft) SOFT=1; shift ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

cluster_exists() { kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; }

if [[ "$SOFT" -eq 1 ]]; then
    echo "[down] soft teardown — cluster '${CLUSTER}' will be kept"
    if cluster_exists; then
        # `helm uninstall` on a missing release is an error, not a no-op, so
        # tolerate it explicitly rather than masking every failure with `|| true`.
        if helm status "$RELEASE" -n "$NAMESPACE" --kube-context "$CONTEXT" >/dev/null 2>&1; then
            helm uninstall "$RELEASE" -n "$NAMESPACE" --kube-context "$CONTEXT"
        else
            echo "[down] no release '${RELEASE}' in namespace '${NAMESPACE}'"
        fi
        kubectl delete namespace "$NAMESPACE" --context "$CONTEXT" --ignore-not-found --wait=true
        echo "[down] namespace '${NAMESPACE}' removed; cluster '${CLUSTER}' still up"
    else
        echo "[down] cluster '${CLUSTER}' not found — nothing to do"
    fi
    exit 0
fi

echo "[down] full teardown — deleting kind cluster '${CLUSTER}'"
if cluster_exists; then
    kind delete cluster --name "$CLUSTER"
    echo "[down] cluster '${CLUSTER}' deleted"
else
    echo "[down] cluster '${CLUSTER}' not found — nothing to do"
fi
