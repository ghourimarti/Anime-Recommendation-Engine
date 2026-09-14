#!/usr/bin/env bash
# scripts/venue/llm_status.sh — which LLM is the RUNNING app actually using?
#
# Reads the live containers, never .env or the Makefile: the routing flag the api
# process sees, which venue engine is running, and — the check that matters —
# whether the api container can reach the venue on the URL it will really call.
#
# Why that last check: an unreachable venue does not raise an error. The router
# falls through to Groq / OpenAI, every answer still arrives, and the GPU sits
# idle. That failure has happened twice (S21.10c: venue on the wrong network;
# Track L: SGLang listening on a different container port), and both times
# everything *looked* healthy.
#
# Usage:  bash scripts/venue/llm_status.sh      (or: make llm-status)
# Exit:   0 mode is consistent · 1 routing on but venue missing or unreachable
#         2 api container not running

set -uo pipefail
export MSYS_NO_PATHCONV=1 # Git Bash: keep URL paths inside docker exec args intact

API=anime-api
NET=${COMPOSE_NET:-anime-recommender_default}
row() { printf '  %-18s %s\n' "$1" "$2"; }

if ! docker ps --filter "name=^${API}$" --format '{{.Names}}' | grep -q .; then
    echo "  api container not running — start it with: make up | make up-vllm | make up-sglang"
    exit 2
fi

routing=$(docker exec "$API" printenv LLM_VENUE_ROUTING_ENABLED 2>/dev/null || echo "unset")
url=$(docker exec "$API" printenv LLM_VENUE_URL 2>/dev/null || echo "unset")
engine=""
for name in anime-vllm anime-sglang; do
    if docker ps --filter "name=^${name}$" --format '{{.Names}}' | grep -q .; then
        engine=${name#anime-}
    fi
done

echo "  ── LLM mode (read from the running containers) ──"
row "api routing flag" "$routing"
row "venue engine" "${engine:-none}"

if [[ "$routing" != "true" ]]; then
    row "mode" "API-based LLM (Groq / OpenAI)"
    if [[ -n "$engine" ]]; then
        row "note" "$engine is running but unused — routing is off"
    fi
    exit 0
fi

if [[ -z "$engine" ]]; then
    row "mode" "WARN  routing is on but no venue runs — every request falls back to Groq / OpenAI"
    exit 1
fi

on_net=$(docker inspect -f "{{if index .NetworkSettings.Networks \"$NET\"}}yes{{else}}no{{end}}" "anime-$engine" 2>/dev/null || echo "?")
code=$(docker exec "$API" python -c \
    "import os, urllib.request as u; print(u.urlopen(os.environ['LLM_VENUE_URL'].rstrip('/') + '/models', timeout=5).status)" \
    2>/dev/null || echo "unreachable")
row "on app network" "$on_net"
row "api → venue" "$code   ($url)"

if [[ "$code" == "200" ]]; then
    row "mode" "SELF-HOSTED $engine — confident queries go to the GPU, the rest to Groq / OpenAI"
    exit 0
fi
row "mode" "WARN  $engine runs but the api cannot reach it — requests silently fall back to Groq / OpenAI"
exit 1
