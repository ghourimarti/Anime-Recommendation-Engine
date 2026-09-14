#!/usr/bin/env bash
# scripts/service_ls.sh — every component of the local stack: live status, URLs
# and, by default, connection details INCLUDING local credentials (L.13).
#
#   make service_ls   full directory with credentials (pgAdmin, MinIO, Langfuse, ...)
#   make urls         the same list with URLs and status only, NO credentials
#                     (printed at the end of make up / upv / up-vllm / up-sglang)
#
# Values are read from .env when this runs, falling back to the compose defaults,
# so the directory cannot drift from what the containers were started with. The
# old `make urls` duplicated ports and passwords as Makefile variables, which
# silently went stale whenever .env changed.
#
# Status is live: container state and health from Docker, plus an HTTP probe for
# every web endpoint. Credentials shown are LOCAL development values. External
# API keys (OpenAI, Groq, Clerk secret) are never printed: they are not service
# logins, and a terminal screenshot should not leak a paid key.
#
# Usage: bash scripts/service_ls.sh [--urls]

set -uo pipefail
cd "$(dirname "$0")/.."

MODE=full
[[ ${1:-} == --urls ]] && MODE=urls

# A .env value without sourcing the file: values contain spaces, and port lines
# carry inline comments ("POSTGRES_PORT=1002   # 1. Postgres").
env_get() {
    local key=$1 default=${2:-} v=""
    if [[ -f .env ]]; then
        v=$(grep -E "^${key}=" .env | tail -n 1 | cut -d= -f2- | tr -d '\r')
        v=${v%%[[:space:]]#*}
        v=$(printf '%s' "$v" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g; s/^"(.*)"$/\1/')
    fi
    printf '%s' "${v:-$default}"
}

POSTGRES_PORT=$(env_get POSTGRES_PORT 1002)
REDIS_PORT=$(env_get REDIS_PORT 1003)
LOCALSTACK_PORT=$(env_get LOCALSTACK_PORT 1004)
API_PORT=$(env_get API_PORT 1005)
WEB_PORT=$(env_get WEB_PORT 1006)
CLICKHOUSE_HTTP_PORT=$(env_get CLICKHOUSE_HTTP_PORT 1007)
CLICKHOUSE_NATIVE_PORT=$(env_get CLICKHOUSE_NATIVE_PORT 1008)
LANGFUSE_POSTGRES_PORT=$(env_get LANGFUSE_POSTGRES_PORT 1009)
LANGFUSE_REDIS_PORT=$(env_get LANGFUSE_REDIS_PORT 1010)
MINIO_API_PORT=$(env_get MINIO_API_PORT 1011)
MINIO_CONSOLE_PORT=$(env_get MINIO_CONSOLE_PORT 1012)
LANGFUSE_WEB_PORT=$(env_get LANGFUSE_WEB_PORT 1013)
OTEL_GRPC_PORT=$(env_get OTEL_GRPC_PORT 1014)
OTEL_HTTP_PORT=$(env_get OTEL_HTTP_PORT 1015)
REDISINSIGHT_PORT=$(env_get REDISINSIGHT_PORT 1016)
OTEL_PROM_PORT=$(env_get OTEL_PROM_PORT 1017)
PROMETHEUS_PORT=$(env_get PROMETHEUS_PORT 1018)
GRAFANA_PORT=$(env_get GRAFANA_PORT 1019)
SGLANG_PORT=${SGLANG_PORT:-1020}   # Makefile SGLANG_PORT / VLLM_PORT (not in .env)
VLLM_PORT=${VLLM_PORT:-1021}

# ─── helpers ─────────────────────────────────────────────────────────────────
status_of() {  # container -> healthy | up | starting | UNHEALTHY | stopped | not running
    local s
    s=$(docker inspect -f '{{.State.Status}}{{if .State.Health}}/{{.State.Health.Status}}{{end}}' "$1" 2>/dev/null) \
        || { printf 'not running'; return; }
    case "$s" in
        running/healthy)   printf 'healthy' ;;
        running/starting)  printf 'starting' ;;
        running/unhealthy) printf 'UNHEALTHY' ;;
        running*)          printf 'up' ;;
        exited*)           printf 'stopped' ;;
        *)                 printf '%s' "${s%%/*}" ;;
    esac
}

http_ok() {  # 2xx/3xx within 3 s
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$1" 2>/dev/null)
    [[ $code =~ ^[23] ]]
}

row()   { printf '  %-30s %-12s %s\n' "$1" "$2" "$3"; }
more()  { printf '  %-30s %-12s %s\n' "" "" "$1"; }
creds() { [[ $MODE == full ]] && more "$1"; return 0; }
section() { printf '\n  [ %s ]\n' "$1"; }

# ─── header ──────────────────────────────────────────────────────────────────
echo
echo "  ============================================================================"
if [[ $MODE == full ]]; then
    echo "   ANIME RECOMMENDER - service directory (LOCAL credentials: never paste anywhere)"
else
    echo "   ANIME RECOMMENDER - services   (connection details + credentials: make service_ls)"
fi
echo "  ============================================================================"

# ─── app ─────────────────────────────────────────────────────────────────────
section "APP"
row "Web (Next.js)" "$(status_of anime-web)" "http://localhost:${WEB_PORT}"
row "API (FastAPI)" "$(status_of anime-api)" "http://localhost:${API_PORT}/docs"
more "health http://localhost:${API_PORT}/health | ready http://localhost:${API_PORT}/ready"
row "Worker (SQS consumer)" "$(status_of anime-worker)" "container anime-worker | queue $(env_get WORKER_QUEUE feedback)"
jobs=""
for j in anime-migrate:migrate anime-sqs-init:sqs-init anime-langfuse-minio-init:minio-bucket; do
    c=${j%%:*} n=${j#*:}
    st=$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$c" 2>/dev/null) || st="missing"
    case "$st" in
        "exited 0") jobs+="$n ok | " ;;
        missing)    jobs+="$n not run | " ;;
        running*)   jobs+="$n running | " ;;
        *)          jobs+="$n FAILED ($st) | " ;;
    esac
done
row "Setup jobs" "" "${jobs% | }"
if [[ $(status_of anime-api) =~ ^(healthy|up|starting)$ ]]; then
    mode=$(bash scripts/venue/llm_status.sh 2>/dev/null | grep -m1 -E '^\s*mode' | sed -E 's/^\s*mode\s+//')
    row "LLM mode" "" "${mode:-unknown (make llm-status)}"
else
    row "LLM mode" "" "api not running"
fi

# ─── inference engines ───────────────────────────────────────────────────────
section "INFERENCE ENGINES (self-hosted GPU)"
for e in "vLLM:anime-vllm:${VLLM_PORT}:metrics /metrics" "SGLang:anime-sglang:${SGLANG_PORT}:server info /get_server_info"; do
    IFS=: read -r name cont port extra <<<"$e"
    st=$(status_of "$cont")
    base="http://localhost:${port}"
    if [[ $st =~ ^(up|healthy)$ ]] && http_ok "${base}/v1/models"; then
        model=$(curl -s --max-time 3 "${base}/v1/models" 2>/dev/null | grep -oE '"id": ?"[^"]+"' | head -n 1 | sed -E 's/.*"([^"]+)"$/\1/')
        row "$name" "serving" "${base}/v1/models  model: ${model:-?}"
        docs=""; http_ok "${base}/docs" && docs="docs ${base}/docs | "
        more "${docs}${extra%% *} ${base}${extra##* } | OpenAI-compatible: ${base}/v1/chat/completions"
    elif [[ $st =~ ^(up|healthy)$ ]]; then
        row "$name" "loading" "${base}/v1/models (not answering yet: make venue-status)"
    else
        row "$name" "$st" "${base}/v1/models  (start: make up-${name,,})"
    fi
done
more "inside the app network both engines answer at http://anime-venue:8000/v1"

# ─── databases ───────────────────────────────────────────────────────────────
section "DATABASES"
PG_DB=$(env_get POSTGRES_DB anime) PG_USER=$(env_get POSTGRES_USER anime) PG_PASS=$(env_get POSTGRES_PASSWORD anime)
row "App Postgres + pgvector" "$(status_of anime-postgres)" "localhost:${POSTGRES_PORT}  database ${PG_DB}"
creds "user ${PG_USER} | password ${PG_PASS}"
creds "pgAdmin: host localhost | port ${POSTGRES_PORT} | maintenance db ${PG_DB} | user ${PG_USER} | password ${PG_PASS}"
creds "URL postgresql://${PG_USER}:${PG_PASS}@localhost:${POSTGRES_PORT}/${PG_DB}"

LF_DB=$(env_get LANGFUSE_DB_NAME langfuse) LF_USER=$(env_get LANGFUSE_DB_USER langfuse) LF_PASS=$(env_get LANGFUSE_DB_PASSWORD langfuse)
row "Langfuse Postgres" "$(status_of anime-langfuse-postgres)" "localhost:${LANGFUSE_POSTGRES_PORT}  database ${LF_DB}"
creds "user ${LF_USER} | password ${LF_PASS}"
creds "pgAdmin: host localhost | port ${LANGFUSE_POSTGRES_PORT} | maintenance db ${LF_DB} | user ${LF_USER} | password ${LF_PASS}"
creds "URL postgresql://${LF_USER}:${LF_PASS}@localhost:${LANGFUSE_POSTGRES_PORT}/${LF_DB}"

row "ClickHouse (Langfuse traces)" "$(status_of anime-langfuse-clickhouse)" "http://localhost:${CLICKHOUSE_HTTP_PORT}/play  native localhost:${CLICKHOUSE_NATIVE_PORT}"
creds "user $(env_get CLICKHOUSE_USER clickhouse) | password $(env_get CLICKHOUSE_PASSWORD clickhouse)"

row "App Redis (cache)" "$(status_of anime-redis)" "localhost:${REDIS_PORT}"
creds "no password (local) | URL redis://localhost:${REDIS_PORT}/0"
row "Langfuse Redis (queue)" "$(status_of anime-langfuse-redis)" "localhost:${LANGFUSE_REDIS_PORT}"
creds "password $(env_get LANGFUSE_REDIS_AUTH langfuse)"
row "RedisInsight (Redis UI)" "$(status_of anime-redisinsight)" "http://localhost:${REDISINSIGHT_PORT}  (both Redis pre-added)"

# ─── storage and queues ──────────────────────────────────────────────────────
section "STORAGE AND QUEUES"
row "MinIO (Langfuse blobs)" "$(status_of anime-langfuse-minio)" "console http://localhost:${MINIO_CONSOLE_PORT}  S3 API http://localhost:${MINIO_API_PORT}"
creds "user $(env_get MINIO_ROOT_USER minio) | password $(env_get MINIO_ROOT_PASSWORD miniosecret) | bucket langfuse"
row "LocalStack (SQS / S3)" "$(status_of anime-localstack)" "http://localhost:${LOCALSTACK_PORT}/_localstack/health"
creds "access key test | secret test | region us-east-1"
more "queues: aws --endpoint-url=http://localhost:${LOCALSTACK_PORT} sqs list-queues"

# ─── observability ───────────────────────────────────────────────────────────
section "OBSERVABILITY"
row "Langfuse (LLM traces)" "$(status_of anime-langfuse-web)" "http://localhost:${LANGFUSE_WEB_PORT}"
creds "login $(env_get LANGFUSE_INIT_USER_EMAIL admin@anime.local) | password $(env_get LANGFUSE_INIT_USER_PASSWORD anime-admin-1234) | project $(env_get LANGFUSE_INIT_PROJECT_ID anime-recommender)"
creds "API keys: public $(env_get LANGFUSE_PUBLIC_KEY '(unset)') | secret $(env_get LANGFUSE_SECRET_KEY '(unset)')"
row "Grafana (dashboards)" "$(status_of anime-grafana)" "http://localhost:${GRAFANA_PORT}"
creds "login $(env_get GRAFANA_ADMIN_USER admin) | password $(env_get GRAFANA_ADMIN_PASSWORD admin)"
row "Prometheus (metrics)" "$(status_of anime-prometheus)" "http://localhost:${PROMETHEUS_PORT}/targets  (no auth)"
row "OTel Collector" "$(status_of anime-otel-collector)" "gRPC localhost:${OTEL_GRPC_PORT} | HTTP http://localhost:${OTEL_HTTP_PORT}"
more "metrics export http://localhost:${OTEL_PROM_PORT}/metrics"

echo
if [[ $MODE == urls ]]; then
    echo "  Credentials and database connection details: make service_ls"
else
    echo "  Not shown on purpose: OpenAI / Groq API keys, Clerk secret key (not service logins)."
fi
echo "  ============================================================================"
echo
