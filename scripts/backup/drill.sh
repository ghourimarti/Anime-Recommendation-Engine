#!/usr/bin/env bash
# scripts/backup/drill.sh — Full local backup+restore drill.
#
# Proves end-to-end that the backups work.
#
# Cycle:
#   1. Capture row counts from LIVE postgres for top tables.
#   2. Dump the live DB to backups/anime_<ts>.sql.gz.
#   3. Spin up a fresh restore-target container (separate compose project).
#   4. Restore the dump into the fresh target.
#   5. Capture row counts from the RESTORED target.
#   6. Compare: live vs restored, per table, fail on mismatch.
#   7. Teardown the restore-target container + volume (unless --keep).
#
# A passing drill means: the backup format + restore path actually work
# end-to-end. A failing drill is the time to discover it, NOT at 3 a.m.
#
# Usage:
#   bash scripts/backup/drill.sh
#   bash scripts/backup/drill.sh --keep       # leave restore target running
#   bash scripts/backup/drill.sh --dry-run

set -euo pipefail

DRY_RUN=0
KEEP=0
TARGET_PORT="${BACKUP_RESTORE_PORT:-55432}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --keep) KEEP=1; shift ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."
SCRIPT_DIR="scripts/backup"

if [[ "$DRY_RUN" -eq 1 ]]; then
    cat <<EOF
[dry-run] would:
  1. row counts: docker compose exec postgres psql -U anime -c "<query>"
  2. bash ${SCRIPT_DIR}/dump_local.sh                            → backups/<latest>.sql.gz
  3. bash ${SCRIPT_DIR}/restore_local.sh backups/<latest>.sql.gz → restore target up
  4. row counts: docker exec <restore-target> psql -c "<query>"
  5. compare counts; fail on mismatch
  6. bash ${SCRIPT_DIR}/restore_local.sh --teardown (unless --keep)
EOF
    exit 0
fi

# Helper: get row counts for top tables as "<table> <count>" lines.
counts_from_live() {
    docker compose exec -T postgres psql -U anime -d anime -At -F" " -c \
        "SELECT relname, n_live_tup
         FROM pg_stat_user_tables
         ORDER BY relname;"
}
counts_from_restored() {
    docker exec -i anime-restore-target-postgres-1 psql -U anime -d anime -At -F" " -c \
        "SELECT relname, n_live_tup
         FROM pg_stat_user_tables
         ORDER BY relname;"
}

echo "[drill] step 1/5 — capturing LIVE row counts"
LIVE_COUNTS="$(counts_from_live)"
echo "${LIVE_COUNTS}" | head -10 | sed 's/^/  /'

echo
echo "[drill] step 2/5 — dumping LIVE postgres"
bash "${SCRIPT_DIR}/dump_local.sh"
DUMP_FILE="$(ls -1t backups/anime_*.sql.gz | head -1)"
echo "  dump file: ${DUMP_FILE}"

echo
echo "[drill] step 3/5 — restoring into fresh target"
bash "${SCRIPT_DIR}/restore_local.sh" "${DUMP_FILE}" --target-port "${TARGET_PORT}"

echo
echo "[drill] step 4/5 — capturing RESTORED row counts"
sleep 2  # let pg_stat catch up
RESTORED_COUNTS="$(counts_from_restored)"
echo "${RESTORED_COUNTS}" | head -10 | sed 's/^/  /'

echo
echo "[drill] step 5/5 — comparing LIVE vs RESTORED"
FAILED=0
# Compare line-by-line; warn on missing tables, fail on mismatched counts.
while IFS= read -r live_line; do
    table=$(echo "$live_line" | awk '{print $1}')
    live_n=$(echo "$live_line" | awk '{print $2}')
    restored_n=$(echo "${RESTORED_COUNTS}" | awk -v t="$table" '$1==t {print $2}')
    if [[ -z "${restored_n}" ]]; then
        echo "  MISSING in restore: ${table} (live=${live_n})"
        FAILED=1
        continue
    fi
    if [[ "${live_n}" != "${restored_n}" ]]; then
        echo "  MISMATCH: ${table} live=${live_n} restored=${restored_n}"
        FAILED=1
    else
        echo "  OK     : ${table} (${live_n} rows)"
    fi
done <<< "${LIVE_COUNTS}"

if [[ "$KEEP" -eq 0 ]]; then
    echo
    echo "[teardown] removing restore target (pass --keep to retain)"
    bash "${SCRIPT_DIR}/restore_local.sh" --teardown
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
    echo "[drill] PASS — backup + restore cycle succeeded end-to-end."
    exit 0
else
    echo "[drill] FAIL — see mismatches above. Backup format or restore path is broken."
    exit 1
fi
