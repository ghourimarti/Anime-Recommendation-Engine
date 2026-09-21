#!/usr/bin/env bash
# scripts/deploy/up_local_k8s.sh — Phase 7 Stage 2 stand-up.
#
# Brings the chart up on a local kind cluster, end to end, from nothing:
#   cluster -> images -> namespace -> secret -> data tier -> helm -> rollout wait
#
# Idempotent: safe to re-run. Images are only re-loaded into the cluster when
# they actually changed (kind load re-archives ~1.5GB otherwise, which is the
# difference between a 20s iteration and a 3min one).
#
# Usage:
#   bash scripts/deploy/up_local_k8s.sh
#   bash scripts/deploy/up_local_k8s.sh --skip-build      # reuse existing :local images
#   bash scripts/deploy/up_local_k8s.sh --recreate        # full cold: delete cluster first
#   bash scripts/deploy/up_local_k8s.sh --help
#
# Env overrides:
#   KIND_CLUSTER   cluster name   (default: anime-local)
#   K8S_NAMESPACE  namespace      (default: anime-local)
#   HELM_RELEASE   release name   (default: anime)
#   IMAGE_TAG      local tag      (default: local)  -- must match values-local.yaml
#
# Exit codes:
#   0 — stack up, all rollouts complete
#   1 — a step failed (message names which)
#   2 — usage error or missing prerequisite

set -euo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
RELEASE="${HELM_RELEASE:-anime}"
TAG="${IMAGE_TAG:-local}"
CONTEXT="kind-${CLUSTER}"
SKIP_BUILD=0
RECREATE=0

CHART="infra/k8s/helm/anime-recommender"
KIND_CFG="infra/k8s/local/kind-config.yaml"
DATATIER="infra/k8s/local/datatier.yaml"
# Contract fixed by values.yaml externalSecrets.targetName — every workload envFroms it.
SECRET_NAME="anime-app-secrets"
# Pinned: an addon that drifts silently is one more variable in every diagnosis.
METRICS_SERVER_VERSION="${METRICS_SERVER_VERSION:-v0.7.2}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-build) SKIP_BUILD=1; shift ;;
        --recreate)   RECREATE=1; shift ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

say() { printf '\n[up] %s\n' "$*"; }
die() { printf '\n[up] ERROR: %s\n' "$*" >&2; exit 1; }

# --- 0. Pre-flight ---------------------------------------------------
say "pre-flight"
for bin in docker kind kubectl helm; do
    command -v "$bin" >/dev/null 2>&1 || { echo "missing: $bin" >&2; exit 2; }
done
docker info >/dev/null 2>&1 || { echo "Docker is not running" >&2; exit 2; }
[[ -f .env ]] || { echo ".env not found — copy .env.example and fill it in" >&2; exit 2; }
[[ -f "$KIND_CFG" ]] || die "missing $KIND_CFG"
[[ -f "$DATATIER" ]] || die "missing $DATATIER"
echo "  ok: docker, kind, kubectl, helm, .env"

# Read one key out of .env without sourcing it (values may contain spaces or #).
get_env() {
    local v
    v="$(grep -E "^${1}=" .env | tail -n1 | cut -d= -f2- || true)"
    v="${v%\"}"
    v="${v#\"}"
    printf '%s' "$v"
}

MISSING=()
for k in OPENAI_API_KEY GROQ_API_KEY CLERK_SECRET_KEY CLERK_JWKS_URL; do
    [[ -n "$(get_env "$k")" ]] || MISSING+=("$k")
done
if (( ${#MISSING[@]} )); then
    die "required .env keys are empty: ${MISSING[*]}"
fi

# --- 1. Cluster ------------------------------------------------------
if (( RECREATE )); then
    say "--recreate: tearing the cluster down first"
    bash scripts/deploy/down_local_k8s.sh
fi

if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
    say "cluster '${CLUSTER}' already exists"
else
    say "creating cluster '${CLUSTER}' (1 control-plane + 2 workers)"
    kind create cluster --name "$CLUSTER" --config "$KIND_CFG" --wait 120s
fi
kubectl config use-context "$CONTEXT" >/dev/null
kubectl get nodes

# --- 2. Images -------------------------------------------------------
IMAGES=("anime-recommender/api:${TAG}" "anime-recommender/web:${TAG}" "anime-recommender/worker:${TAG}")

if (( SKIP_BUILD )); then
    say "--skip-build: reusing existing :${TAG} images"
    for ref in "${IMAGES[@]}"; do
        docker image inspect "$ref" >/dev/null 2>&1 \
            || die "$ref not present and --skip-build was given"
    done
else
    say "building images :${TAG} (same base-image digests as make package)"
    # shellcheck disable=SC1091
    set -a; . ./base-images.lock; set +a
    docker build --build-arg UV_IMAGE="$UV_IMAGE" \
        -f apps/api/Dockerfile -t "anime-recommender/api:${TAG}" .
    docker build --build-arg NODE_IMAGE="$NODE_IMAGE" \
        -f apps/web/Dockerfile -t "anime-recommender/web:${TAG}" apps/web
    docker build --build-arg UV_IMAGE="$UV_IMAGE" \
        -f apps/worker/Dockerfile -t "anime-recommender/worker:${TAG}" .
fi

# kind load re-archives and ships ~500MB per image to every node. Only do it when
# the bytes actually differ from what the node already has.
node_has_image() {
    local node="$1" repo="$2" tag="$3" want="$4" have
    # crictl prints Docker Hub images fully qualified (docker.io/library/redis) while
    # kind-loaded local ones carry no registry. Suffix-match so both compare correctly;
    # an exact match silently reloads every data-tier image on every run.
    have="$(docker exec "$node" crictl images 2>/dev/null \
            | awk -v r="$repo" -v t="$tag" '($1==r || $1 ~ ("/" r "$")) && $2==t {print $3; exit}')" || return 1
    [[ -n "$have" && "$want" == "$have"* ]]
}

# The data tier is pulled from Docker Hub by kubelet unless we hand it over. On a
# cold cluster that measured 3m04s for pgvector alone and timed out the rollout.
# These are already on the host (compose uses them), so loading is a local copy.
DATA_IMAGES=("pgvector/pgvector:pg16" "redis:7-alpine" "localstack/localstack:3")
for ref in "${DATA_IMAGES[@]}"; do
    docker image inspect "$ref" >/dev/null 2>&1 || { echo "  pulling $ref"; docker pull -q "$ref"; }
done

# Preloading the data tier is an OPTIMISATION, not a requirement: if it fails the
# cluster just pulls from Docker Hub instead (slower, but correct). kind runs
# `ctr images import --all-platforms`, which errors with "content digest not found"
# when the host image is a manifest list whose other-platform layers were never
# fetched — a property of how the image was pulled, not of our setup. Letting that
# abort a 10-minute acceptance would be absurd, so these loads are best-effort.
load_best_effort() {
    kind load docker-image "$1" --name "$CLUSTER" 2>/dev/null || {
        echo "    (preload skipped for $1 — kubelet will pull it; see rollout timeouts)"
        return 0
    }
}

say "syncing images into the cluster"
for ref in "${IMAGES[@]}" "${DATA_IMAGES[@]}"; do
    repo="${ref%:*}"
    tag="${ref##*:}"
    want="$(docker image inspect "$ref" --format '{{.Id}}' | sed 's/^sha256://')"
    needs_load=0
    while read -r node; do
        node_has_image "$node" "$repo" "$tag" "$want" || { needs_load=1; break; }
    done < <(kind get nodes --name "$CLUSTER")

    if (( needs_load )); then
        echo "  loading $ref"
        case " ${DATA_IMAGES[*]} " in
            *" $ref "*) load_best_effort "$ref" ;;   # optimisation — may fail
            *) kind load docker-image "$ref" --name "$CLUSTER" ;;  # app image — must succeed
        esac
    else
        echo "  up to date: $ref"
    fi
done

# --- 3. Namespace + Secret -------------------------------------------
say "namespace '${NS}' and secret '${SECRET_NAME}'"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# ESO is disabled locally (values-local.yaml), so this script owns the Secret that
# every workload envFroms. DATABASE_URL/REDIS_URL point at in-cluster Services, NOT
# at the compose ports on the host — the point of Stage 2 is that traffic goes
# through Services and kube-proxy.
kubectl create secret generic "$SECRET_NAME" \
    --namespace "$NS" \
    --from-literal=OPENAI_API_KEY="$(get_env OPENAI_API_KEY)" \
    --from-literal=GROQ_API_KEY="$(get_env GROQ_API_KEY)" \
    --from-literal=CLERK_SECRET_KEY="$(get_env CLERK_SECRET_KEY)" \
    --from-literal=LANGFUSE_SECRET_KEY="$(get_env LANGFUSE_SECRET_KEY)" \
    --from-literal=DATABASE_URL="postgresql+asyncpg://anime:anime@anime-postgres:5432/anime" \
    --from-literal=REDIS_URL="redis://anime-redis:6379/0" \
    --from-literal=AWS_ENDPOINT_URL="http://localstack:4566" \
    --from-literal=AWS_ACCESS_KEY_ID="test" \
    --from-literal=AWS_SECRET_ACCESS_KEY="test" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
# The AWS values are LocalStack placeholders, not credentials — but they must be
# present or the workers die with botocore NoCredentialsError on their first SQS
# poll. AWS_ENDPOINT_URL is deliberately NOT in the chart ConfigMap: on real AWS
# it must stay unset so boto resolves the real endpoints.
echo "  secret has 9 keys (4 from .env, 2 in-cluster Services, 3 LocalStack)"

# --- 4. Data tier ----------------------------------------------------
say "data tier (postgres + redis, outside the chart — same place RDS sits in AWS)"
kubectl apply -n "$NS" -f "$DATATIER"
kubectl -n "$NS" rollout status deploy/anime-postgres --timeout=420s
kubectl -n "$NS" rollout status deploy/anime-redis --timeout=300s
kubectl -n "$NS" rollout status deploy/localstack --timeout=900s

# --- 4a. metrics-server ----------------------------------------------
# Without this the HPA exists but reads `cpu: <unknown>/70%` forever: installed,
# inert, and scaling nothing. An autoscaler that cannot read a metric is worse
# than none — it reads as capacity that is not there.
#
# --kubelet-insecure-tls is REQUIRED on kind and MUST NOT reach cloud: upstream
# metrics-server verifies kubelet serving certs against the cluster CA, and kind's
# kubelet certs are not signed for that. EKS/DOKS have properly signed kubelets,
# so this flag is a local-substrate workaround, not a general setting.
say "metrics-server (HPA needs a metrics source)"
if kubectl -n kube-system get deploy metrics-server >/dev/null 2>&1; then
    echo "  already installed"
else
    kubectl apply -f "https://github.com/kubernetes-sigs/metrics-server/releases/download/${METRICS_SERVER_VERSION}/components.yaml" >/dev/null
    kubectl -n kube-system patch deploy metrics-server --type=json \
        -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]' >/dev/null
    echo "  installed ${METRICS_SERVER_VERSION} (+--kubelet-insecure-tls for kind)"
fi
kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s
# Ready != serving metrics; the first scrape takes another ~15-20s. Poll for a
# real number so the HPA has something to read before anything asserts on it.
printf "  waiting for first metrics scrape"
for _ in $(seq 1 30); do
    if kubectl top nodes >/dev/null 2>&1; then echo " ok"; break; fi
    printf "."
    sleep 3
done

# --- 4b. SQS queues ---------------------------------------------------
# Created BEFORE the workers exist so they do not crash-loop against missing
# queues. The prefix is read from the chart values rather than hardcoded, so it
# cannot drift from the SQS_QUEUE_PREFIX the workers actually read.
SQS_PREFIX="$(awk '/^  sqsQueuePrefix:/{print $2; exit}' "${CHART}/values.yaml")"
say "creating SQS queues in LocalStack (prefix ${SQS_PREFIX})"
INIT_POD="sqs-init-$$"
# Applied as a manifest, not `kubectl run`: this currently runs before Helm
# installs the ResourceQuota, but relying on that ordering is fragile — re-running
# queue init against an installed release would be rejected for missing requests.
kubectl -n "$NS" apply -f - >/dev/null <<POD_EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${INIT_POD}
  labels: { app: sqs-init, tier: bootstrap }
spec:
  restartPolicy: Never
  containers:
    - name: init
      image: anime-recommender/api:${TAG}
      imagePullPolicy: IfNotPresent
      command: ["python", "-c", "import asyncio; from anime_core.sqs import ensure_queues; print(asyncio.run(ensure_queues()))"]
      env:
        - { name: AWS_ENDPOINT_URL,     value: "http://localstack:4566" }
        - { name: AWS_ACCESS_KEY_ID,    value: "test" }
        - { name: AWS_SECRET_ACCESS_KEY, value: "test" }
        - { name: AWS_DEFAULT_REGION,   value: "us-east-1" }
        - { name: SQS_QUEUE_PREFIX,     value: "${SQS_PREFIX}" }
      resources:
        requests: { cpu: 50m, memory: 128Mi }
        limits:   { memory: 512Mi }
POD_EOF
if kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/${INIT_POD}" --timeout=180s >/dev/null 2>&1; then
    kubectl -n "$NS" logs "$INIT_POD" | sed 's/^/  /'
    kubectl -n "$NS" delete pod "$INIT_POD" --ignore-not-found >/dev/null 2>&1 || true
else
    echo "  queue init did not succeed; logs follow" >&2
    kubectl -n "$NS" logs "$INIT_POD" 2>&1 | sed 's/^/  /' >&2
    kubectl -n "$NS" delete pod "$INIT_POD" --ignore-not-found >/dev/null 2>&1 || true
    die "SQS queue initialisation failed"
fi

# --- 5. Chart --------------------------------------------------------
# --wait makes helm block on the migrate-job hook too. Without it the app pods
# race the schema and fail readiness for reasons that look like app bugs.
say "helm upgrade --install ${RELEASE}"
helm upgrade --install "$RELEASE" "$CHART" \
    --namespace "$NS" \
    -f "${CHART}/values.yaml" \
    -f "${CHART}/values-local.yaml" \
    --set namespace="$NS" \
    --set-string config.clerkJwksUrl="$(get_env CLERK_JWKS_URL)" \
    --set-string config.clerkIssuer="$(get_env CLERK_ISSUER)" \
    --set-string config.clerkAudience="$(get_env CLERK_AUDIENCE)" \
    --wait --timeout 10m

say "rollout status"
while read -r d; do
    kubectl -n "$NS" rollout status "$d" --timeout=300s
done < <(kubectl -n "$NS" get deploy -o name)

kubectl -n "$NS" get pods -o wide

# Service names come from the CHART name (anime.name), not the release name, and
# the Services listen on 80 while the container listens on 8000. Discover them so
# a chart rename cannot silently break these hints or the smoke probe.
API_SVC="$(kubectl -n "$NS" get svc -o name | sed 's|^service/||' | grep -E -- '-api$' | head -1)"
WEB_SVC="$(kubectl -n "$NS" get svc -o name | sed 's|^service/||' | grep -E -- '-web$' | head -1)"

printf '\n'
printf "[up] Stack is up on kind cluster '%s' (namespace %s).\n\n" "$CLUSTER" "$NS"
printf "  API:  kubectl -n %s port-forward svc/%s 8000:80\n" "$NS" "${API_SVC:-<api-svc>}"
printf "  Web:  kubectl -n %s port-forward svc/%s 3000:80\n\n" "$NS" "${WEB_SVC:-<web-svc>}"
printf "  Smoke:    make deploy-stage2-smoke\n"
printf "  Teardown: make k8s-down        (delete cluster)\n"
printf "            make k8s-down-soft   (keep cluster, drop the release)\n"
