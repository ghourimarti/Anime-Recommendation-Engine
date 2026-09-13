#!/usr/bin/env bash
# scripts/venue/up_sglang.sh — start the local SGLang venue (S20.3).
#
# Deliberate twin of up_vllm.sh. Same model, same weights volume, same port,
# same effective memory budget and context length — so that bench_venue.py
# measures the ENGINE and nothing else. If you change a knob here, change the
# matching knob in up_vllm.sh or the S20.6 comparison is void.
#
# Parameter parity with vLLM:
#   vLLM --gpu-memory-utilization 0.90  <->  SGLang --mem-fraction-static 0.90
#   vLLM --max-model-len 4096           <->  SGLang --context-length 4096
#   vLLM model as positional arg        <->  SGLang --model-path
#
# Prefix caching is left at each engine's DEFAULT (SGLang RadixAttention on,
# vLLM automatic prefix caching on). Disabling one to "be fair" would measure
# a crippled engine; defaults are what you would actually deploy.
#
# Image notes: ENTRYPOINT is NVIDIA's passthrough wrapper, so the launch
# command is supplied as CMD. The image sets no HF_* env vars, so the weights
# volume mounts at the default /root/.cache/huggingface and is reused as-is.
#
# ONE ENGINE AT A TIME — a 12 GB card holds exactly one 7B model. Run
# `bash scripts/venue/down_venue.sh` before starting the other engine.
#
# Usage:
#   bash scripts/venue/up_sglang.sh
#   bash scripts/venue/up_sglang.sh --mem-frac 0.80 --context-len 2048
#   bash scripts/venue/up_sglang.sh --help
#
# Exit codes:
#   0 — server is up and /v1/models responds
#   1 — startup failed (logs dumped)
#   2 — usage error or preflight failure

set -euo pipefail

CONTAINER=anime-sglang
IMAGE=lmsysorg/sglang:latest
VOLUME=vllm-hf-cache
MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
PORT=8001
MEM_FRAC=0.90
CONTEXT_LEN=4096
WAIT_SECS=300

while [[ $# -gt 0 ]]; do
    case "$1" in
        --mem-frac)    MEM_FRAC="$2";    shift 2 ;;
        --context-len) CONTEXT_LEN="$2"; shift 2 ;;
        --port)        PORT="$2";        shift 2 ;;
        -h|--help)     sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

# ─── Preflight ────────────────────────────────────────────────────────
echo "─── preflight ──────────────────────────────────────────────────"

if ! docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    echo "FAIL  volume '$VOLUME' not found — weights are missing." >&2
    exit 2
fi
echo "  OK    volume $VOLUME present (weights shared with vLLM — no re-download)"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "FAIL  image '$IMAGE' not found — run: docker pull $IMAGE" >&2
    exit 2
fi
echo "  OK    image $IMAGE present"

# Refuse to start alongside vLLM: both would claim ~90% of a 12 GB card.
if docker ps --filter "name=^anime-vllm$" --format '{{.Names}}' | grep -q .; then
    cat >&2 <<EOF
FAIL  anime-vllm is still running. One engine at a time — a 12 GB card
      holds exactly one 7B model. Run first:
          bash scripts/venue/down_venue.sh vllm
EOF
    exit 2
fi
echo "  OK    no competing venue container"

FREE_MIB=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
echo "  INFO  GPU free: ${FREE_MIB} MiB"

# Host quietness matters more than VRAM headroom for tail latency — S19's
# finding. Warn if a busy host would contaminate the comparison.
CONTAINERS=$(docker ps -q 2>/dev/null | wc -l | tr -d ' ')
echo "  INFO  containers running: ${CONTAINERS}"
if [[ "$CONTAINERS" -gt 4 ]]; then
    cat >&2 <<EOF
  WARN  ${CONTAINERS} containers are running. S19 measured a 37x p99 TTFT
        difference between a busy and a quiet host. The vLLM baseline was
        taken with 2 containers running; matching that matters more than
        free VRAM. Stop unrelated stacks for a valid comparison.
EOF
fi

HF_TOKEN="${HUGGING_FACE_HUB_TOKEN:-}"
if [[ -z "$HF_TOKEN" && -f .env ]]; then
    HF_TOKEN=$(grep -E '^(HUGGING_FACE_HUB_TOKEN|HF_TOKEN)=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true)
fi

# ─── Compose network attach ──────────────────────────────────────────────────
# A containerised API cannot reach the venue on localhost:8001 — inside that
# container `localhost` IS the container. This is the same class of bug the
# compose file already guards against for Langfuse ("override BOTH host vars so
# env_file localhost URLs don't leak in").
#
# So the venue joins the app's compose network and claims the alias
# `anime-venue`. BOTH engines claim the same alias, so the app's LLM_VENUE_URL
# is identical no matter which engine is running — the engine stays swappable
# from the app's point of view, which is the whole design.
#
# Only one engine runs at a time (12 GB card), so the alias never collides.
COMPOSE_NET=${COMPOSE_NET:-anime-recommender_default}
NET_ARGS=()
if docker network inspect "$COMPOSE_NET" >/dev/null 2>&1; then
    NET_ARGS=(--network "$COMPOSE_NET" --network-alias anime-venue)
    echo "  OK    joining $COMPOSE_NET as 'anime-venue'"
else
    cat >&2 <<EOF
  WARN  compose network '$COMPOSE_NET' not found — starting on the default
        bridge. A HOST-run API (make dev-api) reaches the venue fine on
        localhost. A CONTAINERISED API (make app) will NOT, and will silently
        fall through to the hosted chain. Start the app tier first, or run the
        API on the host.
EOF
fi


# ─── Idempotency ──────────────────────────────────────────────────────
if docker ps --filter "name=^${CONTAINER}$" --format '{{.Names}}' | grep -q .; then
    echo
    echo "  Container '${CONTAINER}' is already running."
    echo "  Endpoint: http://localhost:${PORT}/v1"
    exit 0
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

# ─── Start ────────────────────────────────────────────────────────────
echo
echo "─── starting SGLang ────────────────────────────────────────────"
echo "  model:       $MODEL"
echo "  port:        $PORT"
echo "  mem-frac:    $MEM_FRAC   (parity with vLLM gpu-util)"
echo "  context-len: $CONTEXT_LEN   (parity with vLLM max-model-len)"

docker run -d \
    --name "$CONTAINER" \
    --gpus all \
    --ipc=host \
    "${NET_ARGS[@]}" \
    --shm-size 16g \
    -p "${PORT}:30000" \
    -v "${VOLUME}:/root/.cache/huggingface" \
    ${HF_TOKEN:+-e HF_TOKEN="$HF_TOKEN"} \
    "$IMAGE" \
    python3 -m sglang.launch_server \
    --model-path "$MODEL" \
    --host 0.0.0.0 \
    --port 30000 \
    --mem-fraction-static "$MEM_FRAC" \
    --context-length "$CONTEXT_LEN" \
    >/dev/null

echo "  container started; waiting up to ${WAIT_SECS}s for /v1/models…"

# ─── Wait for readiness ───────────────────────────────────────────────
for ((i = 0; i < WAIT_SECS; i += 5)); do
    if curl -sf "http://localhost:${PORT}/v1/models" >/dev/null 2>&1; then
        echo
        echo "─── ready ──────────────────────────────────────────────────────"
        echo "  endpoint: http://localhost:${PORT}/v1"
        curl -s "http://localhost:${PORT}/v1/models" 2>/dev/null | head -c 300
        echo
        echo
        echo "  next: make venue-bench ENGINE=sglang"
        exit 0
    fi
    if ! docker ps --filter "name=^${CONTAINER}$" --format '{{.Names}}' | grep -q .; then
        echo >&2
        echo "FAIL  container exited during startup. Last 40 log lines:" >&2
        docker logs --tail 40 "$CONTAINER" 2>&1 >&2 || true
        exit 1
    fi
    sleep 5
    printf '.'
done

echo >&2
echo "FAIL  timed out after ${WAIT_SECS}s. Last 40 log lines:" >&2
docker logs --tail 40 "$CONTAINER" 2>&1 >&2 || true
exit 1
