#!/usr/bin/env bash
# scripts/deploy/status_k8s.sh — is a kind cluster running, and what is on it?
#
# WHY THIS EXISTS
# ---------------
# A kind cluster is Docker containers that outlive the shell that made them, the
# terminal, and a reboot. `make down` tears down the compose stack and does not
# touch it — so a cluster forgotten after a debugging session quietly holds three
# containers and several GB of disk indefinitely, and the usual symptom is "my
# laptop is slow" days later rather than anything pointing back here.
#
# `make ps` calls this alongside the compose and venue status so a stray cluster
# cannot stay invisible. Reporting it is most of the fix; `make k8s-downv` is the
# rest.
#
# Reads the RUNNING cluster, not .env or the Makefile — the same principle as
# scripts/venue/llm_status.sh: report what IS, not what was configured.
#
# Usage:
#   bash scripts/deploy/status_k8s.sh
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace     (default: anime-local)
#
# Exit codes:
#   0 — always. This is a status report, not a gate; `make ps` must not fail
#       because a cluster happens to be down.

set -uo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"

if ! command -v kind >/dev/null 2>&1; then
    echo "  kind: not installed"
    exit 0
fi

if ! kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
    echo "  kind cluster '${CLUSTER}': down"
    exit 0
fi

CONTAINERS="$(docker ps -q --filter "name=${CLUSTER}" 2>/dev/null | wc -l | tr -d ' ')"
# Disk is the part people are surprised by: node images are ~1GB each before any
# workload, and they are not reclaimed until the cluster is deleted.
SIZE="$(docker ps --filter "name=${CLUSTER}" --format '{{.Size}}' 2>/dev/null \
        | awk '{gsub(/[^0-9.]/,"",$1); s+=$1} END {if (s>0) printf "%.1fGB+", s/1024; else printf "?"}')"

echo "  kind cluster '${CLUSTER}': UP — ${CONTAINERS} containers, ~${SIZE} writable layers"
echo "    (outlives 'make down'; remove with 'make k8s-downv')"

kubectl --context "$CONTEXT" get nodes --no-headers 2>/dev/null \
    | awk '{printf "    node %-34s %s\n", $1, $2}'

PODS="$(kubectl --context "$CONTEXT" -n "$NS" get pods --no-headers 2>/dev/null)"
if [[ -n "$PODS" ]]; then
    echo "    namespace ${NS}:"
    # Restarts are surfaced because a pod can read "Running" while having crashed
    # repeatedly — the count is the signal that something is wrong underneath.
    echo "$PODS" | awk '{printf "    pod  %-50s %-12s restarts=%s\n", $1, $3, $4}'
else
    echo "    namespace ${NS}: no pods (chart not installed — 'make k8s-up')"
fi

exit 0
