#!/usr/bin/env bash
# scripts/backup/dump_local.sh — Local Postgres dump from the running compose stack.
#
# Backup discipline: RPO target under 5 minutes.
#
# Output: backups/anime_<utc-timestamp>.sql.gz + .sha256 sidecar.
# Format: pg_dump --clean --if-exists --quote-all-identifiers so restore is safe
#         into a non-empty target (idempotent re-restore is the senior default).
#
# This script does NOT touch the live database — read-only.
#
# Usage:
#   bash scripts/backup/dump_local.sh
#   bash scripts/backup/dump_local.sh --output-dir custom/path
#   bash scripts/backup/dump_local.sh --dry-run

set -euo pipefail

DRY_RUN=0
OUTPUT_DIR="backups"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${OUTPUT_DIR}/anime_${TIMESTAMP}.sql.gz"

if [[ "$DRY_RUN" -eq 1 ]]; then
    cat <<EOF
[dry-run] would:
  1. mkdir -p ${OUTPUT_DIR}
  2. docker compose exec -T postgres pg_dump \\
       --clean --if-exists --quote-all-identifiers \\
       -U anime anime \\
       | gzip > ${OUTPUT_FILE}
  3. compute sha256 → ${OUTPUT_FILE}.sha256
  4. print size + path
EOF
    exit 0
fi

mkdir -p "${OUTPUT_DIR}"

echo "[dump] verifying postgres is running…"
docker compose ps postgres --status running --quiet >/dev/null 2>&1 || {
    echo "error: postgres container not running — start it with: docker compose up -d postgres" >&2
    exit 2
}

echo "[dump] pg_dump → ${OUTPUT_FILE}"
docker compose exec -T postgres pg_dump \
    --clean --if-exists --quote-all-identifiers \
    -U anime anime \
    | gzip > "${OUTPUT_FILE}"

if [[ ! -s "${OUTPUT_FILE}" ]]; then
    echo "error: dump produced an empty file — was the database empty? aborting" >&2
    rm -f "${OUTPUT_FILE}"
    exit 1
fi

echo "[dump] computing sha256…"
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${OUTPUT_FILE}" > "${OUTPUT_FILE}.sha256"
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${OUTPUT_FILE}" > "${OUTPUT_FILE}.sha256"
else
    echo "  (no sha256 tool found — skipping integrity sidecar)"
fi

SIZE=$(du -h "${OUTPUT_FILE}" | cut -f1)
echo
echo "[dump] OK — ${OUTPUT_FILE} (${SIZE})"
echo "[dump] sha256: $(cat "${OUTPUT_FILE}.sha256" 2>/dev/null || echo '(no sidecar)')"
