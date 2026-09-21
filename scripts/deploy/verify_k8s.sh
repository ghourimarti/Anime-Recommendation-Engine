#!/usr/bin/env bash
# scripts/deploy/verify_k8s.sh — P7.4 assertions: probes, HPA, DNS.
#
# WHAT THIS CHECKS THAT THE SMOKE DOES NOT
# ----------------------------------------
# smoke_k8s.sh proves the app answers. This proves the CLUSTER MECHANICS the app
# depends on actually work — the things that look fine until the day they matter:
#
#   probes  configured AND firing. "Ready" proves readiness passed; a restart
#           count of 0 proves liveness is not killing a healthy process. A probe
#           that is merely present in the manifest proves neither.
#   HPA     reading a REAL metric. An HPA with `cpu: <unknown>/70%` is installed,
#           inert, and scaling nothing — worse than absent, because it reads as
#           capacity that is not there. This is exactly the state P7.4 found.
#   DNS     short name AND fully-qualified, resolved from INSIDE a pod. The app
#           working proves same-namespace short names only; cloud manifests and
#           cross-namespace refs use the FQDN form, which can break on its own.
#           Testing from the host would exercise a completely different resolver.
#
# Usage:
#   bash scripts/deploy/verify_k8s.sh
#   bash scripts/deploy/verify_k8s.sh --help
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace     (default: anime-local)
#
# Exit codes:
#   0 — every assertion passed
#   1 — at least one assertion failed
#   2 — usage error / cluster not reachable

set -uo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"

case "${1:-}" in
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    "") ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
esac

cd "$(dirname "$0")/../.."
K() { kubectl --context "$CONTEXT" -n "$NS" "$@"; }

kubectl config get-contexts "$CONTEXT" >/dev/null 2>&1 \
    || { echo "no kubectl context '${CONTEXT}' — is the cluster up? (make k8s-up)" >&2; exit 2; }

FAILED=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*"; FAILED=1; }

API_DEPLOY="$(K get deploy -o name 2>/dev/null | sed 's|^deployment.apps/||' | grep -E -- '-api$' | head -1)"
[[ -n "$API_DEPLOY" ]] || { echo "no *-api deployment in '${NS}' (make k8s-up)" >&2; exit 2; }

# ─── 1. Probes ────────────────────────────────────────────────────────
echo "[1/4] probes — configured AND firing"
for probe in startupProbe livenessProbe readinessProbe; do
    path="$(K get deploy "$API_DEPLOY" \
            -o jsonpath="{.spec.template.spec.containers[0].${probe}.httpGet.path}" 2>/dev/null)"
    if [[ -n "$path" ]]; then
        pass "${probe} configured (${path})"
    else
        fail "${probe} missing on ${API_DEPLOY}"
    fi
done

# Ready means the readiness probe actually succeeded against a live process —
# stronger than reading it back out of the manifest we just wrote.
READY="$(K get deploy "$API_DEPLOY" -o jsonpath='{.status.readyReplicas}' 2>/dev/null)"
[[ "${READY:-0}" -ge 1 ]] \
    && pass "readiness firing — ${READY} ready replica(s)" \
    || fail "no ready replicas; readiness never passed"

# Restarts are how a too-aggressive liveness probe shows up: the app is healthy,
# the probe disagrees, kubelet keeps killing it. Steady-state must be 0.
RESTARTS="$(K get pods -l component=api --no-headers 2>/dev/null | awk '{s+=$4} END {print s+0}')"
[[ "${RESTARTS:-0}" -eq 0 ]] \
    && pass "liveness not false-positiving — 0 restarts" \
    || fail "${RESTARTS} restart(s) on api pods — liveness may be too aggressive"

# ─── 2. metrics pipeline ──────────────────────────────────────────────
echo
echo "[2/4] metrics-server — the HPA's data source"
kubectl --context "$CONTEXT" top nodes >/dev/null 2>&1 \
    && pass "kubectl top nodes returns metrics" \
    || fail "kubectl top nodes failed — metrics-server missing or not scraping"
K top pods >/dev/null 2>&1 \
    && pass "kubectl top pods returns metrics" \
    || fail "kubectl top pods failed — node metrics can work while pod metrics do not"

# ─── 3. HPA ───────────────────────────────────────────────────────────
echo
echo "[3/4] HPA — reading a real metric, not <unknown>"
HPAS="$(K get hpa -o name 2>/dev/null | sed 's|^horizontalpodautoscaler.autoscaling/||')"
if [[ -z "$HPAS" ]]; then
    fail "no HPA in namespace ${NS}"
else
    while read -r h; do
        [[ -n "$h" ]] || continue
        # ScalingActive/ValidMetricFound is the authoritative signal. The TARGETS
        # column is a rendering of it, but the condition states WHY when it is not.
        reason="$(K get hpa "$h" -o jsonpath='{.status.conditions[?(@.type=="ScalingActive")].reason}' 2>/dev/null)"
        cur="$(K get hpa "$h" -o jsonpath='{.status.currentMetrics[0].resource.current.averageUtilization}' 2>/dev/null)"
        if [[ "$reason" == "ValidMetricFound" && -n "$cur" ]]; then
            pass "${h}: ValidMetricFound, cpu ${cur}%"
        else
            fail "${h}: ScalingActive=${reason:-<none>}, metric=${cur:-<unknown>}"
        fi
    done <<< "$HPAS"
fi

# ─── 4. in-cluster DNS ────────────────────────────────────────────────
echo
echo "[4/4] cluster DNS — from inside a pod, short and fully-qualified"
API_POD="$(K get pods -l component=api -o name 2>/dev/null | head -1 | sed 's|^pod/||')"
if [[ -z "$API_POD" ]]; then
    fail "no api pod to resolve from"
else
    for host in "anime-postgres" "anime-postgres.${NS}.svc.cluster.local" "anime-redis" "localstack"; do
        # getent, not nslookup/dig: the runtime image is slim and ships neither,
        # but glibc's resolver is always there and is what the app itself uses.
        if K exec "$API_POD" -- getent hosts "$host" >/dev/null 2>&1; then
            pass "resolves ${host}"
        else
            fail "cannot resolve ${host} from ${API_POD}"
        fi
    done
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
    echo "k8s-verify: PASS"
    exit 0
fi
echo "k8s-verify: FAIL"
exit 1
