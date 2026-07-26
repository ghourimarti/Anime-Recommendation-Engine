#!/usr/bin/env bash
# scripts/backup/restore_local.sh — Restore a dump into a FRESH container.
#
# SAFETY: this script will NEVER restore into the live `postgres` service.
# It spins up a separate compose project ("anime-restore-target") with its
# own postgres container on a different port, restores there, runs a row-count
# sanity check, and leaves the target running for inspection.
#
# Why: "backups" you've never test-restored are not backups. The drill
# (drill.sh) automates the full cycle; this script is the building block.
#
# Usage:
#   bash scripts/backup/restore_local.sh path/to/dump.sql.gz
#   bash scripts/backup/restore_local.sh path/to/dump.sql.gz --target-port 55432
#   bash scripts/backup/restore_local.sh --teardown                 # remove the restore target
#   bash scripts/backup/restore_local.sh --dry-run path/to/dump.sql.gz

set -euo pipefail

PROJECT_NAME="anime-restore-target"
TARGET_PORT=55432
TARGET_CONTAINER="${PROJECT_NAME}-postgres-1"
DRY_RUN=0
TEARDOWN=0
DUMP_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --teardown) TEARDOWN=1; shift ;;
        --target-port) TARGET_PORT="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
        --*) echo "unknown arg: $1" >&2; exit 2 ;;
        *) DUMP_FILE="$1"; shift ;;
    esac
done

cd "$(dirname "$0")/../.."

teardown() {
    echo "[teardown] removing restore-target container + volume…"
    docker rm -f "${TARGET_CONTAINER}" 2>/dev/null || true
    docker volume rm "${PROJECT_NAME}-postgres-data" 2>/dev/null || true
    echo "[teardown] done."
}

if [[ "$TEARDOWN" -eq 1 ]]; then
    teardown
    exit 0
fi

if [[ -z "$DUMP_FILE" ]]; then
    echo "error: pass the dump file as the first argument" >&2
    echo "  bash scripts/backup/restore_local.sh backups/anime_<ts>.sql.gz" >&2
    exit 2
fi
if [[ ! -f "$DUMP_FILE" ]]; then
    echo "error: dump file not found: $DUMP_FILE" >&2
    exit 2
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    cat <<EOF
[dry-run] would:
  1. docker run -d --name ${TARGET_CONTAINER} \\
       -e POSTGRES_USER=anime -e POSTGRES_PASSWORD=anime -e POSTGRES_DB=anime \\
       -p ${TARGET_PORT}:5432 -v ${PROJECT_NAME}-postgres-data:/var/lib/postgresql/data \\
       pgvector/pgvector:pg16
  2. wait for it to accept connections
  3. zcat ${DUMP_FILE} | docker exec -i ${TARGET_CONTAINER} psql -U anime -d anime
  4. row-count sanity check (anime_titles, users — adjust to schema)
  5. leave target running on port ${TARGET_PORT} for inspection
     (run with --teardown to remove)
EOF
    exit 0
fi

# Tear down any previous restore target so this is idempotent.
docker rm -f "${TARGET_CONTAINER}" >/dev/null 2>&1 || true

echo "[restore] spinning up fresh pgvector container as ${TARGET_CONTAINER} on :${TARGET_PORT}…"
docker run -d --name "${TARGET_CONTAINER}" \
    -e POSTGRES_USER=anime \
    -e POSTGRES_PASSWORD=anime \
    -e POSTGRES_DB=anime \
    -p "${TARGET_PORT}:5432" \
    -v "${PROJECT_NAME}-postgres-data:/var/lib/postgresql/data" \
    pgvector/pgvector:pg16 >/dev/null

echo "[restore] waiting for postgres to accept connections…"
for i in $(seq 1 30); do
    if docker exec "${TARGET_CONTAINER}" pg_isready -U anime -d anime >/dev/null 2>&1; then
        echo "  ready after ${i}s"
        break
    fi
    sleep 1
done

echo "[restore] zcat ${DUMP_FILE} | psql"
if [[ "${DUMP_FILE##*.}" == "gz" ]]; then
    zcat "${DUMP_FILE}" | docker exec -i "${TARGET_CONTAINER}" psql -U anime -d anime -v ON_ERROR_STOP=1 -q
else
    docker exec -i "${TARGET_CONTAINER}" psql -U anime -d anime -v ON_ERROR_STOP=1 -q < "${DUMP_FILE}"
fi

echo
echo "[verify] row counts on the restored target:"
docker exec "${TARGET_CONTAINER}" psql -U anime -d anime -c \
    "SELECT relname AS table_name, n_live_tup AS rows
     FROM pg_stat_user_tables
     ORDER BY n_live_tup DESC
     LIMIT 10;"

cat <<EOF

[done] Restore target running on localhost:${TARGET_PORT} as ${TARGET_CONTAINER}.
       Inspect it directly with:
         psql -h localhost -p ${TARGET_PORT} -U anime -d anime
       (password: anime)

       When finished, remove it with:
         bash scripts/backup/restore_local.sh --teardown
EOF
