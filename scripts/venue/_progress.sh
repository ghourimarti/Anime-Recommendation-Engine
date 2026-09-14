#!/usr/bin/env bash
# scripts/venue/_progress.sh — live startup progress for the GPU venue scripts (L.11).
#
# Sourced by up_vllm.sh and up_sglang.sh. Replaces a silent row of dots with the
# phases the engine itself logs, so a slow start is visibly moving:
#
#   [ 0:14] python starting
#   [ 5:49] weights loaded (62.15 s)
#   [ 5:52] KV cache ready: 42669 tokens
#   [ 7:40] still capturing CUDA graphs 21/42 | last log 3s ago
#   [11:30] SERVING on :1020  (11 m 30 s)
#
# Why each rule exists (measured on this RTX 3060, 2026-09-13/14):
#   - heartbeat every 60 s: CUDA-graph capture alone ran 316-396 s with few log lines
#   - silence is a WARNING, not a failure: a legitimate phase can be quiet for
#     minutes, and killing a slow-but-healthy engine is the bug this replaces
#   - fail FAST on a dead container or CUDA out-of-memory: those never recover,
#     so waiting out the full timeout would only hide them
#   - a Python traceback is shown but not fatal on its own: engines log
#     recoverable tracebacks; the container exiting is the real signal
#
# Every grep reads a here-string, never `printf | grep -q`: under the callers'
# `set -o pipefail`, grep -q exiting early makes printf take SIGPIPE and the
# pipeline report "no match" on a large log (the P6.9 render-verify lesson).
#
# Usage:  watch_startup <vllm|sglang> <container> <host_port> <wait_secs>
# Env:    STALL_WARN_SECS (default 300) | HEARTBEAT_SECS (default 60)
# Return: 0 once /v1/models answers | 1 on exit, fatal error or timeout (log tail printed)

_vp_elapsed() {  # mm:ss since epoch $1
    local s=$(( $(date +%s) - $1 ))
    printf '%2d:%02d' $((s / 60)) $((s % 60))
}

# "label::extended-regex" per engine, in startup order. A phase that never
# appears (e.g. no torch.compile) is simply skipped.
_vp_phases() {
    case "$1" in
        sglang)
            cat <<'EOF'
python starting::CUDA Version
config parsed::server_args=
initialising torch distributed::Init torch distributed begin
loading weights::Load weight begin
weights loaded::Load weight end
KV cache ready::KV Cache is allocated
capturing CUDA graphs::Capture (target prefill )?[Cc][Uu][Dd][Aa] graph begin
CUDA graphs captured::Capture (target decode )?[Cc][Uu][Dd][Aa] graph end
starting HTTP server::Uvicorn running|Application startup complete|fired up
EOF
            ;;
        vllm)
            cat <<'EOF'
config parsed::non-default args
loading weights::Starting to load model
weights loaded::Model loading took
compiling (torch.compile)::torch\.compile takes|Dynamo bytecode transform time
KV cache ready::GPU KV cache size
capturing CUDA graphs::Capturing CUDA graph
engine initialised::init engine .* took
starting HTTP server::Starting vLLM API server|Application startup complete
EOF
            ;;
    esac
}

# Extra detail for a phase, pulled from the log. Always returns 0.
_vp_detail() {
    local engine=$1 label=$2 logs=$3 v=""
    case "$label" in
        "weights loaded")
            if [[ $engine == sglang ]]; then
                v=$(grep -m1 'Load weight end' <<<"$logs" | grep -oE 'elapsed=[0-9.]+' | cut -d= -f2 || true)
                [[ -n $v ]] && printf ' (%s s)' "$v"
            else
                v=$(grep -m1 'Model loading took' <<<"$logs" | grep -oE '[0-9.]+ GiB memory and [0-9.]+ seconds' || true)
                [[ -n $v ]] && printf ' (%s)' "$v"
            fi
            ;;
        "KV cache ready")
            v=$(grep -m1 -E 'KV Cache is allocated|GPU KV cache size' <<<"$logs" \
                | grep -oE '#tokens: [0-9]+|size: [0-9,]+ tokens' | grep -oE '[0-9,]+' | head -n 1 || true)
            [[ -n $v ]] && printf ': %s tokens' "$v"
            ;;
        "capturing CUDA graphs")
            v=$(grep -E 'Capturing' <<<"$logs" | tail -n 1 | grep -oE '[0-9]+/[0-9]+' | tail -n 1 || true)
            [[ -n $v ]] && printf ' %s' "$v"
            ;;
    esac
    return 0
}

watch_startup() {
    local engine=$1 container=$2 port=$3 wait_secs=$4
    local stall=${STALL_WARN_SECS:-300} beat=${HEARTBEAT_SECS:-60}
    local t0 now logs nlines last_n=-1 last_change last_beat
    local phase_idx=-1 phase_label="starting container" warned_stall=0 warned_tb=0
    local -a labels=() regexes=()
    local line i s

    while IFS= read -r line; do
        [[ -z $line ]] && continue
        labels+=("${line%%::*}")
        regexes+=("${line#*::}")
    done < <(_vp_phases "$engine")

    t0=$(date +%s)
    last_change=$t0
    last_beat=$t0
    printf '  [%s] container started; watching its log (heartbeat %ss, warn after %ss of silence)\n' \
        "$(_vp_elapsed "$t0")" "$beat" "$stall"

    while :; do
        now=$(date +%s)

        if curl -sf --max-time 5 "http://localhost:${port}/v1/models" >/dev/null 2>&1; then
            s=$(( now - t0 ))
            printf '  [%s] SERVING on :%s  (%d m %02d s)\n' "$(_vp_elapsed "$t0")" "$port" $((s / 60)) $((s % 60))
            return 0
        fi

        if [[ -z $(docker ps -q --filter "name=^${container}$" 2>/dev/null) ]]; then
            printf '\n  FAIL  [%s] container exited during "%s". Last 40 log lines:\n' "$(_vp_elapsed "$t0")" "$phase_label" >&2
            docker logs --tail 40 "$container" 2>&1 | tr '\r' '\n' | tail -n 40 >&2 || true
            return 1
        fi

        logs=$(docker logs "$container" 2>&1 | tr '\r' '\n' || true)
        nlines=$(grep -c . <<<"$logs" || true)
        if [[ $nlines != "$last_n" ]]; then
            last_n=$nlines
            last_change=$now
            warned_stall=0
        fi

        # Never recovers: stop now instead of at the timeout.
        if grep -qE 'CUDA out of memory|OutOfMemoryError|Engine core initialization failed' <<<"$logs"; then
            printf '\n  FAIL  [%s] out of GPU memory / engine init failed during "%s". Last 40 log lines:\n' \
                "$(_vp_elapsed "$t0")" "$phase_label" >&2
            tail -n 40 <<<"$logs" >&2
            return 1
        fi

        if (( ! warned_tb )) && grep -q 'Traceback (most recent call last)' <<<"$logs"; then
            warned_tb=1
            printf '  [%s] WARN  the engine logged a Python traceback (fatal only if the container exits):\n' "$(_vp_elapsed "$t0")"
            grep -A 12 'Traceback (most recent call last)' <<<"$logs" | head -n 13 | sed 's/^/          /' || true
        fi

        # Print every newly reached phase, in startup order.
        for (( i = phase_idx + 1; i < ${#labels[@]}; i++ )); do
            if grep -qE "${regexes[$i]}" <<<"$logs"; then
                phase_idx=$i
                phase_label=${labels[$i]}
                printf '  [%s] %s%s\n' "$(_vp_elapsed "$t0")" "$phase_label" "$(_vp_detail "$engine" "$phase_label" "$logs")"
                last_beat=$now
            fi
        done

        if (( now - last_beat >= beat )); then
            printf '  [%s] still %s%s | last log %ss ago\n' "$(_vp_elapsed "$t0")" "$phase_label" \
                "$([[ $phase_label == "capturing CUDA graphs" ]] && _vp_detail "$engine" "$phase_label" "$logs")" \
                $((now - last_change))
            last_beat=$now
        fi

        if (( ! warned_stall && now - last_change >= stall )); then
            warned_stall=1
            printf '  [%s] WARN  no new log output for %ss during "%s" (still waiting). Last line: %s\n' \
                "$(_vp_elapsed "$t0")" $(( now - last_change )) "$phase_label" \
                "$(grep . <<<"$logs" | tail -n 1 | cut -c1-120)"
        fi

        if (( now - t0 >= wait_secs )); then
            printf '\n  FAIL  timed out after %ss during "%s". Last 40 log lines:\n' "$wait_secs" "$phase_label" >&2
            tail -n 40 <<<"$logs" >&2
            return 1
        fi

        sleep 5
    done
}
