#!/usr/bin/env bash
# scripts/venue/down_venue.sh — stop local GPU venue containers and free VRAM.
#
# PLAN DEVIATION (S19.6 #4): the walkthrough specified `down_vllm.sh`. Writing
# one venue-agnostic teardown instead avoids a near-identical `down_sglang.sh`
# in S20, and makes the "only one engine at a time" constraint explicit in a
# single place. The 12 GB card holds exactly one 7B model, so teardown is a
# hard prerequisite for S20.3 — not a nicety.
#
# Usage:
#   bash scripts/venue/down_venue.sh            # stop all venue containers
#   bash scripts/venue/down_venue.sh vllm       # stop just vLLM
#   bash scripts/venue/down_venue.sh sglang     # stop just SGLang
#   bash scripts/venue/down_venue.sh --help
#
# Exit codes:
#   0 — nothing running, or containers stopped successfully
#   2 — usage error

set -euo pipefail

ALL_CONTAINERS=(anime-vllm anime-sglang)

case "${1:-}" in
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    "")        TARGETS=("${ALL_CONTAINERS[@]}") ;;
    vllm)      TARGETS=(anime-vllm) ;;
    sglang)    TARGETS=(anime-sglang) ;;
    *)         echo "unknown target: $1 (expected vllm|sglang or nothing)" >&2; exit 2 ;;
esac

FREE_BEFORE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ' || echo "")

stopped=0
for name in "${TARGETS[@]}"; do
    if docker ps -a --filter "name=^${name}$" --format '{{.Names}}' | grep -q .; then
        echo "  stopping ${name}…"
        # `rm` as well as `stop`: on some driver versions a stopped-but-present
        # container keeps the GPU device reservation, and the next engine then
        # fails to allocate for no visible reason.
        docker rm -f "$name" >/dev/null
        stopped=$((stopped + 1))
    fi
done

if [[ "$stopped" -eq 0 ]]; then
    echo "  nothing to stop — no venue containers present"
    exit 0
fi

# The driver does not always release immediately; give it a moment before
# reporting, otherwise the "after" number understates what was actually freed.
sleep 3
FREE_AFTER=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ' || echo "")

echo
if [[ -n "$FREE_BEFORE" && -n "$FREE_AFTER" ]]; then
    echo "  VRAM free: ${FREE_BEFORE} MiB → ${FREE_AFTER} MiB  (reclaimed $((FREE_AFTER - FREE_BEFORE)) MiB)"
else
    echo "  stopped ${stopped} container(s)"
fi
echo "  GPU is now free for the other engine."
