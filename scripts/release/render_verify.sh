#!/usr/bin/env bash
# scripts/release/render_verify.sh — render every vendor x env and validate it (P6.9).
#
# Three checks, because each catches a different way a chart can look "valid":
#
#   1. RENDER    helm template succeeds for every vendor x env combination.
#
#   2. SCHEMA    kubeconform -strict against Kubernetes schemas AND CRD schemas.
#                Without CRD schemas, -strict errors on every CRD; the usual "fix",
#                -ignore-missing-schemas, reports "0 errors" by SKIPPING them — no
#                validation at all on the Rollout, ScaledObjects and ExternalSecret,
#                the resources most likely to be wrong. Both schema sources are
#                pinned to a commit, for the reason base images are pinned by
#                digest: a gate validating against a moving `master` is not
#                reproducible.
#
#   3. CONTRACT  which CRD kinds a vendor may emit. kubeconform validates schemas,
#                not whether the cluster runs the controller: a kind render that
#                contains a Rollout passes schema validation and then fails on
#                install. This turns that into a render-time failure.
#
# Plus NEGATIVE CONTROLS: each check is fed a known-bad input and must reject it,
# for the right reason. A gate that cannot fail is decoration.
#
# FETCH, THEN VALIDATE OFFLINE. Letting kubeconform download schemas while it
# validates made this gate flaky: raw.githubusercontent.com throttles 12 renders'
# worth of parallel requests, kubeconform retries only 3 times, and it probes the
# Kubernetes location first for every CRD — a 503 there is a hard error, so it
# never falls through to the CRD catalog. First runs failed 2–3 of 12 renders on
# download errors with zero invalid manifests. So: collect the distinct
# apiVersion/kind pairs, fetch each schema once (curl retries 429/5xx with
# backoff) from the right source, then validate against local files only.
# A schema missing from both is still an ERROR — the gate fails CLOSED.
#
# pipefail is load-bearing. `kubeconform ... | tail` exits 0 on INVALID manifests
# because $? is tail's — found while building this gate.
#
# Usage:  bash scripts/release/render_verify.sh
#         KUBECONFORM_CACHE=<dir> to relocate the schema cache
# Exit:   0 every check passed · 1 any render / schema / contract / control failure

set -euo pipefail
cd "$(dirname "$0")/../.."

CHART=infra/k8s/helm/anime-recommender
# = infra/terraform/modules/eks var.kubernetes_version (1.31).
K8S_VERSION=1.31.0
K8S_SCHEMAS_SHA=970cc70507e1880a7a3b64184b6aad417a1d8d85 # yannh/kubernetes-json-schema, pinned 2026-09-13
CATALOG_SHA=ad3b08c5045129d7bb1eeffd8e61719b2c8dd1e2     # datreeio/CRDs-catalog,        pinned 2026-09-13
K8S_BASE="https://raw.githubusercontent.com/yannh/kubernetes-json-schema/${K8S_SCHEMAS_SHA}/v${K8S_VERSION}-standalone-strict"
CRD_BASE="https://raw.githubusercontent.com/datreeio/CRDs-catalog/${CATALOG_SHA}"
VENDORS=(local doks aws)
ENVS=(none dev staging prod)
CRD_KINDS='^kind: (Rollout|AnalysisTemplate|ScaledObject|ExternalSecret)$'

# Safe to persist across runs: every input is pinned, so the name identifies the contents.
CACHE="${KUBECONFORM_CACHE:-$HOME/.cache/kubeconform}/k8s-v${K8S_VERSION}-${K8S_SCHEMAS_SHA:0:12}_crds-${CATALOG_SHA:0:12}"
if command -v cygpath >/dev/null 2>&1; then
    CACHE=$(cygpath -m "$CACHE") # Git Bash: kubeconform is a native exe, give it C:/... paths
fi

for tool in helm kubeconform curl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "FAIL  $tool is not installed" >&2
        exit 1
    fi
done

OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

validate() {
    # Local files only — no network, so no flaky results. No -ignore-missing-schemas:
    # a resource with no schema in either location is an error.
    kubeconform -strict -summary \
        -schema-location "$CACHE/k8s/{{.ResourceKind}}{{.KindSuffix}}.json" \
        -schema-location "$CACHE/crds/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json" \
        "$1"
}

# fetch <url> <dest> — 0 if the schema is cached or downloaded. On failure prints
# only the FINAL HTTP status: the attempts --retry absorbs are not failures, and
# logging each one made a passing run look broken.
fetch() {
    [[ -s "$2" ]] && return 0
    mkdir -p "$(dirname "$2")"
    local code
    # --retry covers timeouts, 429 and 5xx (the throttling). A 404 is NOT retried:
    # a wrong path is a real failure, not a transient one.
    code=$(curl -sL --retry 6 --retry-delay 2 --connect-timeout 10 \
        -o "$2.part" -w '%{http_code}' "$1") || true
    if [[ "$code" == 200 ]]; then
        mv "$2.part" "$2"
        return 0
    fi
    rm -f "$2.part"
    echo "HTTP ${code:-no response}"
    return 1
}

fail=0

# ─── 1. render ───────────────────────────────────────────────────────────────
echo "─── 1/3 render: ${#VENDORS[@]} vendors x ${#ENVS[@]} envs ───"
rendered_count=0
for vendor in "${VENDORS[@]}"; do
    for env in "${ENVS[@]}"; do
        args=(-f "$CHART/values.yaml" -f "$CHART/values-$vendor.yaml")
        if [[ "$env" != none ]]; then
            args+=(-f "$CHART/values-$env.yaml")
        fi
        rendered="$OUT/$vendor-$env.yaml"
        if helm template anime "$CHART" "${args[@]}" >"$rendered" 2>"$OUT/$vendor-$env.err"; then
            rendered_count=$((rendered_count + 1))
        else
            echo "  FAIL  render    $vendor x $env"
            sed 's/^/          /' "$OUT/$vendor-$env.err"
            rm -f "$rendered" # absent file = skipped by the phases below
            fail=1
        fi
    done
done
echo "  $rendered_count / $((${#VENDORS[@]} * ${#ENVS[@]})) rendered"

# ─── 2. fetch schemas (pinned, once, cached) ─────────────────────────────────
echo
echo "─── 2/3 schemas: k8s v$K8S_VERSION @ ${K8S_SCHEMAS_SHA:0:7} · CRDs @ ${CATALOG_SHA:0:7} ───"
shopt -s nullglob
renders=("$OUT"/*.yaml)
shopt -u nullglob
pairs=""
if ((${#renders[@]})); then
    pairs=$(awk '/^apiVersion: /{a=$2} /^kind: /{print a, $2}' "${renders[@]}" | sort -u)
fi
ready=0
total=0
while read -r api kind; do
    [[ -z "$api" ]] && continue
    total=$((total + 1))
    k=$(printf '%s' "$kind" | tr '[:upper:]' '[:lower:]')
    if [[ "$api" == */* ]]; then
        group=${api%/*} ver=${api#*/}
    else
        group="" ver=$api
    fi
    # Built-in API groups are dotless (apps, batch, autoscaling) or *.k8s.io;
    # anything else is a CRD. File naming mirrors kubeconform's KindSuffix.
    if [[ -z "$group" || "$group" != *.* || "$group" == *.k8s.io ]]; then
        suffix="-$ver"
        [[ -n "$group" ]] && suffix="-${group%%.*}-$ver"
        url="$K8S_BASE/$k$suffix.json" dest="$CACHE/k8s/$k$suffix.json"
    else
        url="$CRD_BASE/$group/${k}_$ver.json" dest="$CACHE/crds/$group/${k}_$ver.json"
    fi
    if status=$(fetch "$url" "$dest"); then
        ready=$((ready + 1))
    else
        echo "  FAIL  no schema for $kind ($api): $status — $url"
        fail=1
    fi
done <<<"$pairs"
echo "  $ready / $total schemas ready   cache: $CACHE"

# ─── 3. validate + contract ──────────────────────────────────────────────────
echo
echo "─── 3/3 schema + contract ───"
for vendor in "${VENDORS[@]}"; do
    for env in "${ENVS[@]}"; do
        label="$vendor x $env"
        rendered="$OUT/$vendor-$env.yaml"
        [[ -f "$rendered" ]] || continue

        if ! summary=$(validate "$rendered" 2>&1); then
            echo "  FAIL  schema    $label"
            printf '%s\n' "$summary" | sed 's/^/          /'
            fail=1
            continue
        fi

        # Contract: kind has no Argo Rollouts, KEDA or ESO controller.
        if [[ "$vendor" == local ]] && grep -qE "$CRD_KINDS" "$rendered"; then
            echo "  FAIL  contract  $label — emits CRDs kind cannot run:"
            grep -E "$CRD_KINDS" "$rendered" | sort | uniq -c | sed 's/^/          /'
            fail=1
            continue
        fi

        counts=$(printf '%s\n' "$summary" | tail -n 1 | sed 's/.*file - //')
        printf '  PASS  %-16s %s\n' "$label" "$counts"
    done
done

# ─── negative controls ───────────────────────────────────────────────────────
echo
echo "─── negative controls: each check must be able to FAIL ───"

# Schema: an unknown field in a CRD, rejected FOR THAT FIELD. Any other non-zero
# exit (a missing schema, a crash) would otherwise count as "correctly rejected".
control="$OUT/aws-dev.yaml"
if [[ -s "$control" ]] && grep -q "minReplicaCount:" "$control"; then
    sed 's/minReplicaCount:/minReplicaCountTYPO:/' "$control" >"$OUT/control-typo.yml"
    if out=$(validate "$OUT/control-typo.yml" 2>&1); then
        echo "  FAIL  schema    a ScaledObject with an unknown field PASSED — this check cannot fail"
        fail=1
    elif grep -q "minReplicaCountTYPO" <<<"$out"; then
        echo "  PASS  schema    unknown field in a ScaledObject rejected, for that field"
    else
        echo "  FAIL  schema    control rejected for a DIFFERENT reason — inconclusive:"
        printf '%s\n' "$out" | sed 's/^/          /'
        fail=1
    fi
else
    echo "  FAIL  schema    no usable aws x dev render to corrupt (did it fail above?)"
    fail=1
fi

# Fail-closed: a kind with no schema anywhere must ERROR, not be skipped.
cat >"$OUT/control-unknown.yml" <<'EOF'
apiVersion: example.com/v1
kind: Widget
metadata:
  name: control
EOF
if out=$(validate "$OUT/control-unknown.yml" 2>&1); then
    echo "  FAIL  closed    a kind with no schema PASSED — missing schemas are being skipped"
    fail=1
elif grep -qi "could not find schema" <<<"$out"; then
    echo "  PASS  closed    kind with no schema is an error, not a skip"
else
    echo "  FAIL  closed    control rejected for a DIFFERENT reason — inconclusive:"
    printf '%s\n' "$out" | sed 's/^/          /'
    fail=1
fi

# Contract: a local render forced to emit a Rollout must be caught.
forced="$OUT/control-forced-rollout.yml"
if helm template anime "$CHART" -f "$CHART/values.yaml" -f "$CHART/values-local.yaml" \
        --set rollout.enabled=true >"$forced" 2>&1 && grep -qE "$CRD_KINDS" "$forced"; then
    echo "  PASS  contract  local render with rollout.enabled=true detected"
else
    echo "  FAIL  contract  a forced Rollout in a local render went undetected"
    fail=1
fi

echo
if [[ "$fail" -ne 0 ]]; then
    echo "render-verify: FAIL"
    exit 1
fi
echo "render-verify: PASS"
