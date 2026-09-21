#!/usr/bin/env bash
# scripts/backup/drill_k8s.sh — backup+restore drill against the IN-CLUSTER Postgres.
#
# WHY THIS EXISTS SEPARATELY FROM drill.sh
# ----------------------------------------
# drill.sh is compose-coupled: it depends on `make up-data` and shells
# `docker compose exec postgres`. Running it during a Stage 2 acceptance would
# start the compose stack and drill the WRONG database — passing while testing
# nothing the cluster introduced. Stage 2's Postgres is a different substrate
# (PVC-backed, reached through a Service, restored into a scheduled pod), so it
# needs a drill that actually touches that substrate.
#
# Cycle (mirrors drill.sh so the two are comparable):
#   1. ANALYZE + capture row counts from the LIVE in-cluster Postgres.
#   2. pg_dump the live DB out through kubectl exec → backups/anime_k8s_<ts>.sql.gz
#   3. Schedule a fresh restore-target pod (same image, emptyDir — no PVC needed).
#   4. Restore the dump into it through kubectl exec.
#   5. ANALYZE + capture row counts from the RESTORED target.
#   6. Compare live vs restored per table; fail on mismatch or missing table.
#   7. Delete the restore-target pod (unless --keep).
#
# ROW COUNTS ARE TAKEN AFTER ANALYZE ON PURPOSE
# ---------------------------------------------
# pg_stat_user_tables.n_live_tup is a statistics ESTIMATE maintained by the
# stats collector, not a count. On a freshly restored database it reads 0 until
# stats exist, which makes a naive comparison flaky (drill.sh papers over this
# with `sleep 2`). ANALYZE on both sides makes the estimate exact for static
# tables, so the comparison is deterministic rather than timing-dependent.
#
# Usage:
#   bash scripts/backup/drill_k8s.sh
#   bash scripts/backup/drill_k8s.sh --keep      # leave the restore target running
#   bash scripts/backup/drill_k8s.sh --dry-run
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace     (default: anime-local)
#
# Exit codes:
#   0 — PASS, dump + restore verified
#   1 — FAIL (mismatch, or a step failed)
#   2 — usage error / prerequisite missing

set -euo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"
PG_DEPLOY="deploy/anime-postgres"
TARGET_POD="anime-restore-target"
PG_IMAGE="pgvector/pgvector:pg16"
DRY_RUN=0
KEEP=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --keep)    KEEP=1; shift ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

K() { kubectl --context "$CONTEXT" -n "$NS" "$@"; }

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] would:"
    echo "  1. K exec ${PG_DEPLOY} -- psql -c ANALYZE; then read pg_stat_user_tables"
    echo "  2. K exec ${PG_DEPLOY} -- pg_dump  → backups/anime_k8s_<ts>.sql.gz"
    echo "  3. K run ${TARGET_POD} --image=${PG_IMAGE}"
    echo "  4. gunzip -c <dump> | K exec -i ${TARGET_POD} -- psql"
    echo "  5. K exec ${TARGET_POD} -- psql -c ANALYZE; then read counts"
    echo "  6. compare counts; fail on mismatch"
    echo "  7. K delete pod ${TARGET_POD} (unless --keep)"
    exit 0
fi

command -v kubectl >/dev/null 2>&1 || { echo "missing: kubectl" >&2; exit 2; }
kubectl config get-contexts "$CONTEXT" >/dev/null 2>&1 \
    || { echo "no kubectl context '${CONTEXT}' — is the cluster up? (make k8s-up)" >&2; exit 2; }
K get "$PG_DEPLOY" >/dev/null 2>&1 \
    || { echo "${PG_DEPLOY} not found in namespace '${NS}' (make k8s-up)" >&2; exit 2; }

COUNTS_SQL="SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname;"

cleanup_target() {
    if [[ "$KEEP" -eq 0 ]]; then
        K delete pod "$TARGET_POD" --ignore-not-found --wait=false >/dev/null 2>&1 || true
    fi
}
trap cleanup_target EXIT

echo "[drill-k8s] step 1/6 — ANALYZE + capture LIVE row counts"
K exec "$PG_DEPLOY" -- psql -U anime -d anime -q -c "ANALYZE;" >/dev/null
LIVE_COUNTS="$(K exec "$PG_DEPLOY" -- psql -U anime -d anime -At -F" " -c "$COUNTS_SQL")"
echo "${LIVE_COUNTS}" | head -10 | sed 's/^/  /'

echo
echo "[drill-k8s] step 2/6 — dumping LIVE postgres out of the cluster"
mkdir -p backups
DUMP_FILE="backups/anime_k8s_$(date -u +%Y%m%dT%H%M%SZ).sql.gz"
# --clean --if-exists so the restore is idempotent against a non-empty target.
K exec "$PG_DEPLOY" -- pg_dump -U anime -d anime --clean --if-exists | gzip > "$DUMP_FILE"
echo "  dump file: ${DUMP_FILE} ($(du -h "$DUMP_FILE" | cut -f1))"
[[ -s "$DUMP_FILE" ]] || { echo "  FAIL: dump is empty" >&2; exit 1; }

echo
echo "[drill-k8s] step 3/6 — scheduling fresh restore target"
K delete pod "$TARGET_POD" --ignore-not-found --wait=true >/dev/null 2>&1 || true
# Applied as a manifest rather than `kubectl run` because the chart installs a
# ResourceQuota (templates/isolation.yaml) that REJECTS any pod without explicit
# cpu/memory requests. That is the quota doing its job; helper pods have to play
# by the same rules as the workloads.
K apply -f - >/dev/null <<POD_EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${TARGET_POD}
  labels: { app: anime-restore-target, tier: drill }
spec:
  restartPolicy: Never
  containers:
    - name: postgres
      image: ${PG_IMAGE}
      env:
        - { name: POSTGRES_USER,     value: anime }
        - { name: POSTGRES_PASSWORD, value: anime }
        - { name: POSTGRES_DB,       value: anime }
      resources:
        requests: { cpu: 100m, memory: 256Mi }
        limits:   { memory: 1Gi }
POD_EOF
K wait --for=condition=Ready "pod/${TARGET_POD}" --timeout=180s >/dev/null
# Ready means the container started; Postgres itself may still be running initdb.
for _ in $(seq 1 60); do
    if K exec "$TARGET_POD" -- pg_isready -U anime -d anime >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
K exec "$TARGET_POD" -- pg_isready -U anime -d anime >/dev/null \
    || { echo "  FAIL: restore target never became ready" >&2; exit 1; }
echo "  ${TARGET_POD} ready"

echo
echo "[drill-k8s] step 4/6 — restoring dump into the fresh target"
# ON_ERROR_STOP so a broken dump fails here instead of silently restoring half a
# schema and passing the count comparison on the tables that happened to load.
gunzip -c "$DUMP_FILE" \
    | K exec -i "$TARGET_POD" -- psql -U anime -d anime -q -v ON_ERROR_STOP=1 >/dev/null
echo "  restore completed without error"

echo
echo "[drill-k8s] step 5/6 — ANALYZE + capture RESTORED row counts"
K exec "$TARGET_POD" -- psql -U anime -d anime -q -c "ANALYZE;" >/dev/null
RESTORED_COUNTS="$(K exec "$TARGET_POD" -- psql -U anime -d anime -At -F" " -c "$COUNTS_SQL")"
echo "${RESTORED_COUNTS}" | head -10 | sed 's/^/  /'

echo
echo "[drill-k8s] step 6/6 — comparing LIVE vs RESTORED"
FAILED=0
TABLES=0
while IFS= read -r live_line; do
    [[ -n "$live_line" ]] || continue
    table="$(echo "$live_line" | awk '{print $1}')"
    live_n="$(echo "$live_line" | awk '{print $2}')"
    restored_n="$(echo "${RESTORED_COUNTS}" | awk -v t="$table" '$1==t {print $2}')"
    TABLES=$((TABLES + 1))
    if [[ -z "${restored_n}" ]]; then
        echo "  MISSING in restore: ${table} (live=${live_n})"
        FAILED=1
    elif [[ "${live_n}" != "${restored_n}" ]]; then
        echo "  MISMATCH: ${table} live=${live_n} restored=${restored_n}"
        FAILED=1
    else
        echo "  OK     : ${table} (${live_n} rows)"
    fi
done <<< "${LIVE_COUNTS}"

# An empty live DB would compare "0 tables equal 0 tables" and pass while proving
# nothing. Treat that as a failure: the drill needs data to be meaningful.
if [[ "$TABLES" -eq 0 ]]; then
    echo "  FAIL: no user tables found in the live database — has migrate/ingest run?"
    FAILED=1
fi

if [[ "$KEEP" -eq 1 ]]; then
    echo
    echo "[drill-k8s] --keep: restore target left running as pod/${TARGET_POD}"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
    echo "[drill-k8s] PASS — ${TABLES} tables matched; dump + restore verified on the cluster."
    exit 0
fi
echo "[drill-k8s] FAIL — see above. Backup format or restore path is broken."
exit 1
