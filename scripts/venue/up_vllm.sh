#!/usr/bin/env bash
# scripts/venue/up_vllm.sh — start the local vLLM venue (S19.6).
#
# Reproducible server start with pinned flags. Not a manual `docker run`,
# because S20.3 needs the SGLang twin and the comparison is only honest if
# both engines are started the same deliberate way.
#
# Carries forward two hard-won fixes from S19.5:
#   S19.5a — VLLM_USE_V2_MODEL_RUNNER=0 works around the UVA allocation error
#   S19.5b — HF token is passed explicitly so the hub client authenticates
#
# CLI notes for this image (entrypoint is ["vllm","serve"], so docker args
# become `vllm serve <args>`):
#   - the model is a POSITIONAL argument; `--model X` is deprecated
#   - `--disable-log-requests` was removed; passing it aborts startup
#
# Weights come from the `vllm-hf-cache` Docker volume (5.2 GB, verified
# complete in S19.5c). Nothing is downloaded at startup.
#
# Usage:
#   bash scripts/venue/up_vllm.sh
#   bash scripts/venue/up_vllm.sh --gpu-util 0.80 --max-len 2048
#   bash scripts/venue/up_vllm.sh --help
#
# Exit codes:
#   0 — server is up and /v1/models responds
#   1 — startup failed (logs dumped)
#   2 — usage error or preflight failure

set -euo pipefail

CONTAINER=anime-vllm
IMAGE=vllm/vllm-openai:latest
VOLUME=vllm-hf-cache
MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
PORT=8001
GPU_UTIL=0.90
MAX_LEN=4096
WAIT_SECS=300

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu-util) GPU_UTIL="$2"; shift 2 ;;
        --max-len)  MAX_LEN="$2";  shift 2 ;;
        --port)     PORT="$2";     shift 2 ;;
        -h|--help)  sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
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
echo "  OK    volume $VOLUME present"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "FAIL  image '$IMAGE' not found — run: docker pull $IMAGE" >&2
    exit 2
fi
echo "  OK    image $IMAGE present"

# VRAM headroom. The model needs ~5.5 GB of weights plus KV cache; if the
# desktop is holding most of the card this run will either OOM or produce
# numbers about your browser rather than about vLLM.
FREE_MIB=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
echo "  INFO  GPU free: ${FREE_MIB} MiB"
if [[ -n "$FREE_MIB" && "$FREE_MIB" -lt 6000 ]]; then
    cat >&2 <<EOF
  WARN  Only ${FREE_MIB} MiB free — the model needs ~5.5 GB of weights plus
        KV cache. Windows WDDM may page desktop allocations out, but the
        resulting throughput number will reflect memory pressure, not the
        engine. Close Chrome / VS Code / Electron apps for a clean reading.
        Proceeding anyway in 5s (Ctrl-C to abort)…
EOF
    sleep 5
fi

# HF token (S19.5b). Optional for this public model, but passed when present
# so the hub client does not emit the unauthenticated warning.
HF_TOKEN="${HUGGING_FACE_HUB_TOKEN:-}"
if [[ -z "$HF_TOKEN" && -f .env ]]; then
    HF_TOKEN=$(grep -E '^(HUGGING_FACE_HUB_TOKEN|HF_TOKEN)=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'"'"' \r' || true)
fi
[[ -n "$HF_TOKEN" ]] && echo "  OK    HF token present" || echo "  INFO  no HF token (fine — model is public)"

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
    echo "  To restart: bash scripts/venue/down_vllm.sh && bash $0"
    exit 0
fi
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true

# ─── Start ────────────────────────────────────────────────────────────
echo
echo "─── starting vLLM ──────────────────────────────────────────────"
echo "  model:    $MODEL"
echo "  port:     $PORT"
echo "  gpu-util: $GPU_UTIL"
echo "  max-len:  $MAX_LEN"

docker run -d \
    --name "$CONTAINER" \
    --gpus all \
    --ipc=host \
    "${NET_ARGS[@]}" \
    -p "${PORT}:8000" \
    -v "${VOLUME}:/root/.cache/huggingface" \
    -e VLLM_USE_V2_MODEL_RUNNER=0 \
    ${HF_TOKEN:+-e HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"} \
    "$IMAGE" \
    "$MODEL" \
    --gpu-memory-utilization "$GPU_UTIL" \
    --max-model-len "$MAX_LEN" \
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
        echo "  next: make venue-bench"
        exit 0
    fi
    # Fail fast if the container died rather than burning the full timeout.
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
