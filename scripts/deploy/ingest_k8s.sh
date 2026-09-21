#!/usr/bin/env bash
# scripts/deploy/ingest_k8s.sh — load the corpus into the IN-CLUSTER Postgres.
#
# WHY THIS IS A HOST-SIDE JOB AND NOT A K8S JOB
# ---------------------------------------------
# The api image ships the ingestion CODE (packages/ingestion) but deliberately
# not the corpus: apps/api/Dockerfile copies packages/, apps/api/, migrations/
# and alembic.ini — data/ is not in the image and should not be. Baking a
# 230 KB CSV into a production image to make a local acceptance easier would
# mean the artifact we sign, scan and deploy carries a dev fixture.
#
# Alternatives considered:
#   - ConfigMap-mount the CSV into a Job: fits under the 1 MB limit, but puts a
#     dev fixture into cluster state and needs a Job template that only ever
#     runs locally.
#   - COPY data/ into the image: pollutes the shipped artifact. No.
#   - Port-forward + run the existing CLI from the host: reuses the exact code
#     path Stage 1 proves, changes nothing about the image, and matches how
#     ingestion actually happens against a managed DB in cloud — an operational
#     task run against an endpoint, not something the app image does at boot.
# The third is what this does.
#
# Usage:
#   bash scripts/deploy/ingest_k8s.sh
#   bash scripts/deploy/ingest_k8s.sh --csv data/other.csv --port 15432
#   bash scripts/deploy/ingest_k8s.sh --help
#
# Env overrides:
#   KIND_CLUSTER   cluster name  (default: anime-local)
#   K8S_NAMESPACE  namespace     (default: anime-local)
#
# Exit codes:
#   0 — corpus ingested
#   1 — ingestion failed, or Postgres never became reachable
#   2 — usage error / prerequisite missing

set -euo pipefail

CLUSTER="${KIND_CLUSTER:-anime-local}"
NS="${K8S_NAMESPACE:-anime-local}"
CONTEXT="kind-${CLUSTER}"
CSV="data/anime_with_synopsis.csv"
# 15432, not 5432: a compose Postgres may already hold the usual port, and
# ingesting into the WRONG database is a silent, expensive mistake.
PORT=15432

while [[ $# -gt 0 ]]; do
    case "$1" in
        --csv)  CSV="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

cd "$(dirname "$0")/../.."

command -v kubectl >/dev/null 2>&1 || { echo "missing: kubectl" >&2; exit 2; }
command -v uv >/dev/null 2>&1 || { echo "missing: uv" >&2; exit 2; }
[[ -f "$CSV" ]] || { echo "corpus not found: ${CSV}" >&2; exit 2; }
kubectl config get-contexts "$CONTEXT" >/dev/null 2>&1 \
    || { echo "no kubectl context '${CONTEXT}' — is the cluster up? (make k8s-up)" >&2; exit 2; }
kubectl --context "$CONTEXT" -n "$NS" get svc anime-postgres >/dev/null 2>&1 \
    || { echo "svc/anime-postgres not found in '${NS}' (make k8s-up)" >&2; exit 2; }

PF_PID=""
cleanup() {
    if [[ -n "$PF_PID" ]] && kill -0 "$PF_PID" 2>/dev/null; then
        kill "$PF_PID" 2>/dev/null || true
        wait "$PF_PID" 2>/dev/null || true
    fi
    return 0
}
trap cleanup EXIT INT TERM

echo "[ingest] port-forward svc/anime-postgres ${PORT}:5432"
kubectl --context "$CONTEXT" -n "$NS" port-forward svc/anime-postgres "${PORT}:5432" \
    >/dev/null 2>&1 &
PF_PID=$!

# Poll rather than sleep: the tunnel is not usable the instant kubectl forks.
ready=0
for _ in $(seq 1 30); do
    if ! kill -0 "$PF_PID" 2>/dev/null; then
        echo "  FAIL  port-forward exited early" >&2
        exit 1
    fi
    # Bash's /dev/tcp is enough to know the tunnel accepts connections; we do not
    # need a psql client on the host for that.
    if (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null; then
        exec 3<&- 3>&- 2>/dev/null || true
        ready=1
        break
    fi
    sleep 1
done
(( ready )) || { echo "  FAIL  127.0.0.1:${PORT} never accepted a connection" >&2; exit 1; }
echo "  OK    tunnel up"

echo
echo "[ingest] loading ${CSV} into the cluster database"
# Same CLI `make ingest` runs — only DATABASE_URL differs, which is the whole
# point: one ingestion code path, two substrates.
#
# The exit code is captured EXPLICITLY rather than left to `set -e`. Under `make`
# this script once reported failure after the CLI had visibly succeeded (full
# result JSON printed, 269 rows committed), with no error of its own — an exit
# status arriving from somewhere other than the work itself. Whatever the source,
# a status that disagrees with the observable outcome is not something to leave
# implicit in a gate: decide it here, and say which command decided it.
set +e
DATABASE_URL="postgresql+asyncpg://anime:anime@127.0.0.1:${PORT}/anime" \
    uv run python -m anime_ingestion.cli --csv "$CSV"
ingest_rc=$?
set -e

# VERIFY THE OUTCOME, NOT THE EXIT STATUS
# ---------------------------------------
# Inside `make deploy-stage2` this script has twice reported failure after the
# CLI visibly succeeded — full result JSON printed, rows committed — and without
# printing any of its own error paths. It does not reproduce standalone. The
# status is real (make saw it) but does not correspond to anything that failed.
#
# So the gate asks the database instead. "Is the corpus in Postgres" is what this
# step is actually for; an exit code is only ever a proxy for it. Checking the
# thing itself is both more robust and a better gate — a CLI that exits 0 having
# written nothing would now be caught too, which the status check never could.
echo
echo "[ingest] verifying rows landed in the cluster database"
ROWS="$(kubectl --context "$CONTEXT" -n "$NS" exec deploy/anime-postgres -- \
        psql -U anime -d anime -At -c 'SELECT count(*) FROM anime_chunks;' 2>/dev/null \
        | tr -d '\r ' || true)"
ROWS="${ROWS:-0}"

if ! [[ "$ROWS" =~ ^[0-9]+$ ]] || [[ "$ROWS" -eq 0 ]]; then
    echo "[ingest] FAILED — anime_chunks is empty (CLI exit was ${ingest_rc})" >&2
    exit 1
fi

if [[ "$ingest_rc" -ne 0 ]]; then
    echo "[ingest] NOTE: CLI exited ${ingest_rc} but ${ROWS} rows are present."
    echo "[ingest]       Status disagreed with outcome; gating on the outcome."
fi

echo "[ingest] done — ${ROWS} chunks in the in-cluster Postgres"
# Explicit: the EXIT trap tears down the port-forward, and any status leaking out
# of teardown must not turn a verified-good ingest into a failed gate.
exit 0
