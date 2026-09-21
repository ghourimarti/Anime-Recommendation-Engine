#!/usr/bin/env bash
# scripts/deploy/kind_power.sh — stop/start a kind cluster WITHOUT destroying it.
#
# WHY STOP AND DELETE ARE DIFFERENT THINGS
# ----------------------------------------
# A kind cluster is Docker containers holding etcd, so there are two very
# different ways to make it stop consuming resources:
#
#   docker stop   frees CPU and RAM, keeps the cluster and all its state.
#                 Restart is seconds. Disk is still held.
#   kind delete   frees everything including disk. Rebuild is ~5 minutes plus
#                 re-loading ~4GB of images.
#
# Conflating them is why `make down` used to leave the cluster running: deleting
# on every `down` would be hostile (a 5-minute rebuild because you stopped working
# for an hour), so nothing happened at all. Stopping is the behaviour that was
# actually wanted, and it maps onto the compose lifecycle exactly:
#
#   make down   -> stop nodes,   keep cluster   (compose: stop containers, keep volumes)
#   make downv  -> delete cluster               (compose: down -v, volumes gone)
#   make up     -> start nodes
#
# CAVEAT WORTH KNOWING
# --------------------
# A restarted cluster is not identical to a fresh one. kubelet re-establishes, the
# CNI settles, and every pod restarts — so restart counters jump and a pod can sit
# NotReady for a minute. That is also why pods in this project have shown double-
# digit restarts after a laptop suspend/resume: same mechanism. Functionally fine;
# just do not read those counters as application instability.
#
# Usage:
#   bash scripts/deploy/kind_power.sh stop
#   bash scripts/deploy/kind_power.sh start
#
# WHY `start` WAITS ON PODS AND NOT ON NODES
# -----------------------------------------
# Measured on resume: all 3 nodes report Ready after ~8s, but postgres, api and
# localstack are still 0/1 at that moment and the namespace does not settle until
# ~40s. Returning "ready" on node status would therefore be a gate that cannot
# fail in any useful way - it reports success while nothing can serve a request.
# So `start` waits for every pod in the namespace to be Ready.
#
# It also requires readiness to hold for TWO consecutive polls. Recovery is not
# monotonic: the observed sequence was 9/11 -> 6/11 -> 8/11 -> 11/11 as readiness
# probes cycled and pods that looked up went down again. A single all-Ready
# reading can be sampled in a gap between failures.
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace to wait for on start (default: anime-local)
#
# Exit codes:
#   0 — done, INCLUDING "no cluster exists, nothing to do". These run as part of
#       `make up`/`down`, so a missing cluster must never fail the compose
#       lifecycle — you should be able to use this repo without ever touching kind.
#   2 — usage error

set -uo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"

cd "$(dirname "$0")/../.."

command -v kind >/dev/null 2>&1 || { echo "  kind: not installed - skipping"; exit 0; }

cluster_exists() { kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; }

# -a: stopped containers must be found too, or `start` can never see them.
nodes() { docker ps -aq --filter "name=^${CLUSTER}-" 2>/dev/null; }

case "${1:-}" in
  stop)
      if ! cluster_exists; then
          echo "  kind '${CLUSTER}': not present - nothing to stop"
          exit 0
      fi
      ids="$(nodes)"
      if [[ -z "$ids" ]]; then
          echo "  kind '${CLUSTER}': no containers found"
          exit 0
      fi
      running="$(docker ps -q --filter "name=^${CLUSTER}-" | wc -l | tr -d ' ')"
      if [[ "$running" -eq 0 ]]; then
          echo "  kind '${CLUSTER}': already stopped"
          exit 0
      fi
      # shellcheck disable=SC2086
      docker stop $ids >/dev/null 2>&1
      echo "  kind '${CLUSTER}': stopped ${running} node(s) - cluster KEPT (make up restarts it)"
      echo "                    disk is still held; 'make downv' reclaims it"
      ;;
  start)
      if ! cluster_exists; then
          # Deliberately not creating one here. `make up` should not silently
          # trigger a 5-minute cluster build plus a 4GB image load; that belongs
          # behind an explicit `make k8s-upv`.
          echo "  kind: no cluster '${CLUSTER}' - skipping (make k8s-upv to create one)"
          exit 0
      fi
      ids="$(nodes)"
      [[ -n "$ids" ]] || { echo "  kind '${CLUSTER}': no containers to start"; exit 0; }
      # shellcheck disable=SC2086
      docker start $ids >/dev/null 2>&1
      printf "  kind '%s': starting nodes" "$CLUSTER"

      # Stage 1: nodes. Poll rather than sleep - the API server takes a variable
      # time to answer after its container returns, so a fixed sleep is either
      # wasteful or wrong.
      nodes_ready=0
      for _ in $(seq 1 60); do
          if kubectl --context "$CONTEXT" get nodes >/dev/null 2>&1; then
              notready="$(kubectl --context "$CONTEXT" get nodes --no-headers 2>/dev/null                           | grep -cv ' Ready ')"
              [[ "${notready:-1}" -eq 0 ]] && { nodes_ready=1; break; }
          fi
          printf "."
          sleep 2
      done
      if [[ "$nodes_ready" -ne 1 ]]; then
          echo
          echo "  WARN kind '${CLUSTER}' nodes not all Ready after ~2min - 'make k8s-ps' to inspect" >&2
          exit 0     # a slow cluster must not fail the whole `make up`
      fi
      echo " nodes ready"

      # Stage 2: the workload. See the header note - this is the half that decides
      # whether the cluster can actually serve anything.
      pods() { kubectl --context "$CONTEXT" -n "$NS" get pods --no-headers 2>/dev/null; }
      if [[ -z "$(pods)" ]]; then
          echo "  kind '${CLUSTER}': cluster up, no workload in namespace '${NS}'"
          exit 0
      fi
      printf "  waiting for pods in '%s'" "$NS"
      streak=0; rdy=0; tot=0
      for _ in $(seq 1 40); do
          out="$(pods)"
          tot="$(printf '%s
' "$out" | grep -c .)"
          # a[2]!="0" guards against a 0/0 pod counting as ready
          rdy="$(printf '%s
' "$out"                  | awk '{split($2,a,"/"); if (a[1]==a[2] && a[2]!="0") c++} END{print c+0}')"
          if [[ "$tot" -gt 0 && "$rdy" -eq "$tot" ]]; then
              streak=$((streak + 1))
              [[ "$streak" -ge 2 ]] && { echo " ready (${rdy}/${tot})"; exit 0; }
          else
              streak=0
          fi
          printf "."
          sleep 5
      done
      echo
      echo "  WARN pods not all Ready after ~3min (${rdy}/${tot} ready) - try 'make k8s-ps', 'make k8s-verify'" >&2
      exit 0     # report honestly, but do not fail `make up`
      ;;
  -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "usage: $0 {stop|start}" >&2; exit 2 ;;
esac
