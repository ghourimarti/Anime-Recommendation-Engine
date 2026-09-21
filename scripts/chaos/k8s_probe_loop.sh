#!/usr/bin/env bash
# scripts/chaos/k8s_probe_loop.sh — availability probe that runs DURING a drill.
#
# WHY THE PROBE RUNS INSIDE THE CLUSTER
# -------------------------------------
# The obvious approach — `kubectl port-forward` on the host, curl in a loop — is
# invalid for these drills. port-forward binds to ONE specific pod. Kill that pod
# and the tunnel dies, so the loop records failures caused by the instrument
# rather than by the system: you measure your own measurement apparatus.
#
# This runs as a pod that hits the SERVICE name, so requests go through kube-proxy
# exactly as any in-cluster client's would, and individual backend pods dying is
# precisely the thing the Service is supposed to hide.
#
# WHY IT IS PINNED TO THE CONTROL-PLANE NODE
# ------------------------------------------
# k8s_node_drain.sh drains a WORKER. A probe scheduled on that worker would be
# evicted mid-drill and stop measuring at the exact moment the measurement
# matters. Pinning it to the control-plane (with the matching toleration) keeps
# the instrument outside the blast radius.
#
# WHY /ready AND NOT /health
# --------------------------
# /health means the process is alive. /ready means it can actually serve — it
# checks the database. A drill that passes on /health can hide a pod that is up
# and useless, which is the failure mode worth catching.
#
# Usage:
#   bash scripts/chaos/k8s_probe_loop.sh start
#   ... perform a disruption ...
#   bash scripts/chaos/k8s_probe_loop.sh report      # stats, keeps probing
#   bash scripts/chaos/k8s_probe_loop.sh stop        # stats + delete the pod
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace     (default: anime-local)
#   PROBE_INTERVAL seconds between requests (default: 0.2 => ~5/s)
#
# Exit codes:
#   0 — ok  (for `report`/`stop`: ALSO 0 when failures occurred; the drill script
#            decides pass/fail, this only measures)
#   2 — usage error / cluster not reachable

set -uo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"
POD="anime-availability-probe"
INTERVAL="${PROBE_INTERVAL:-0.2}"

cd "$(dirname "$0")/../.."
K() { kubectl --context "$CONTEXT" -n "$NS" "$@"; }

kubectl config get-contexts "$CONTEXT" >/dev/null 2>&1 \
    || { echo "no kubectl context '${CONTEXT}' — is the cluster up? (make k8s-up)" >&2; exit 2; }

API_SVC="$(K get svc -o name 2>/dev/null | sed 's|^service/||' | grep -E -- '-api$' | head -1)"
API_DEPLOY="$(K get deploy -o name 2>/dev/null | sed 's|^deployment.apps/||' | grep -E -- '-api$' | head -1)"
# Reuse the api's own image: it is already on every node (kind load), so the probe
# needs no pull, and it is guaranteed to have python. Resolved from the deployment
# by NAME — `component` is a pod-template label, not a Deployment label, so a
# label selector on Deployments silently matches nothing.
IMAGE="$(K get deploy "${API_DEPLOY:-none}" -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null)"

start_probe() {
    [[ -n "$API_SVC" ]] || { echo "no *-api service in ${NS}" >&2; exit 2; }
    [[ -n "$IMAGE" ]] || { echo "could not determine api image" >&2; exit 2; }
    K delete pod "$POD" --ignore-not-found --wait=true >/dev/null 2>&1

    # python, not curl: the runtime image is slim and ships no curl, but python is
    # guaranteed present — it is what the app runs on. One line per request so the
    # report step can count exactly, including the gap between failures.
    K apply -f - >/dev/null <<POD_EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${POD}
  labels: { app: anime-availability-probe, tier: drill }
spec:
  restartPolicy: Never
  # Stay off the workers so a node drain cannot evict the instrument.
  nodeSelector:
    node-role.kubernetes.io/control-plane: ""
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
  containers:
    - name: probe
      image: ${IMAGE}
      imagePullPolicy: IfNotPresent
      command:
        - python
        - -c
        - |
          import time, urllib.request, sys
          url = "http://${API_SVC}/ready"
          while True:
              t = time.time()
              try:
                  with urllib.request.urlopen(url, timeout=3) as r:
                      print("%.3f OK %d" % (t, r.status), flush=True)
              except Exception as e:
                  print("%.3f FAIL %s" % (t, type(e).__name__), flush=True)
              time.sleep(${INTERVAL})
      resources:
        requests: { cpu: 25m, memory: 64Mi }
        limits:   { memory: 256Mi }
POD_EOF
    K wait --for=condition=Ready "pod/${POD}" --timeout=120s >/dev/null 2>&1 \
        || { echo "  probe pod never became Ready" >&2; K describe pod "$POD" | tail -15 >&2; exit 2; }
    echo "  probe running on $(K get pod "$POD" -o jsonpath='{.spec.nodeName}') -> http://${API_SVC}/ready"
}

report_probe() {
    local logs ok fail total gap
    logs="$(K logs "$POD" 2>/dev/null)"
    if [[ -z "$logs" ]]; then
        echo "  no probe samples (was it started?)" >&2
        return 1
    fi
    ok="$(grep -c ' OK ' <<<"$logs")"
    fail="$(grep -c ' FAIL ' <<<"$logs")"
    total=$(( ok + fail ))
    # Longest unbroken run of failures — a single blip and a 30s outage can share
    # the same failure count, and only one of them is an incident.
    gap="$(awk '/ FAIL /{c++; if(c>m) m=c} / OK /{c=0} END{print m+0}' <<<"$logs")"
    echo "  samples=${total} ok=${ok} fail=${fail} longest-consecutive-fail=${gap}"
    PROBE_TOTAL="$total"; PROBE_OK="$ok"; PROBE_FAIL="$fail"; PROBE_GAP="$gap"
    export PROBE_TOTAL PROBE_OK PROBE_FAIL PROBE_GAP
    printf '%s %s %s %s\n' "$total" "$ok" "$fail" "$gap" > /tmp/anime_probe_stats
    return 0
}

case "${1:-}" in
    start)  start_probe ;;
    report) report_probe ;;
    stop)   report_probe; K delete pod "$POD" --ignore-not-found --wait=false >/dev/null 2>&1; echo "  probe stopped" ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) echo "usage: $0 {start|report|stop}" >&2; exit 2 ;;
esac
