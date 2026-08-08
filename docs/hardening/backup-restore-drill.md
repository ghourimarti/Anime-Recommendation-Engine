# Backup + Restore Drill

Backups you've never test-restored aren't backups. The local drill
(`make backup-drill` / `scripts/backup/drill.sh`) automates the full
dump → fresh container → restore → row-count verification cycle so the
restore path is exercised, not assumed.

**Implements:** the single-instance Postgres backup path (restore tested)
and the RPO < 5 min / RTO < 30 min NFRs.

---

## 1. Local drill (this doc's focus)

### One-command drill

```bash
make backup-drill
# OR explicitly:
bash scripts/backup/drill.sh
```

This:

1. Captures LIVE row counts per table.
2. Dumps the live DB to `backups/anime_<ts>.sql.gz` + sha256 sidecar.
3. Spins a fresh `pgvector/pgvector:pg16` container as `anime-restore-target-postgres-1` on port `55432`.
4. Restores the dump into it.
5. Captures RESTORED row counts.
6. Compares — passes iff every table matches.
7. Tears down the restore target (use `--keep` to inspect after).

### What good looks like

| Signal | Expected |
|---|---|
| Drill exit code | **0** |
| Final line | `[drill] PASS — backup + restore cycle succeeded end-to-end.` |
| Row counts | Every live table matches the restored one |
| Dump file | Exists at `backups/anime_<ts>.sql.gz`, > 0 bytes, sha256 sidecar present |
| Restore target after teardown | `docker ps -a` shows no `anime-restore-target-*` containers; `docker volume ls` shows no associated volumes |

### What BAD looks like

| Symptom | Diagnosis |
|---|---|
| `[drill] FAIL` with MISMATCH rows | The dump format is missing a table OR pg_dump's `--clean --if-exists` dropped a sequence value. Inspect the dump (`zcat … | head -200`) for missing CREATE TABLE statements. |
| Dump file 0 bytes | Live postgres is empty (run `make db-migrate && make ingest` first). |
| Restore exit non-zero | Dump is corrupt OR target's `pgvector` version doesn't match live's. Check `docker compose exec postgres psql -c "SELECT version();"` vs the restore target. |
| Drill hangs at "waiting for postgres to accept connections" | Port 55432 is in use. Pass `--target-port 55433`. |

---

## 2. Local building blocks

The drill chains two lower-level scripts; both are usable independently:

```bash
# Just dump (no restore test)
bash scripts/backup/dump_local.sh
bash scripts/backup/dump_local.sh --output-dir /tmp/scratch

# Restore an existing dump into the fresh target (leaves it running)
bash scripts/backup/restore_local.sh backups/anime_<ts>.sql.gz

# Clean up the restore target
bash scripts/backup/restore_local.sh --teardown
```

The drill is the one to schedule; the building blocks are for one-off
investigation (e.g. "I have a dump from last week — does it still
restore?").

---

## 3. Cloud PITR (documented here, executed in the cloud)

Cloud-side, RDS handles backups automatically via the Terraform module
(`infra/terraform/modules/rds`):

- **Automated backups**: enabled, 7-day retention window (TF default).
- **PITR**: continuously available within the retention window.
- **Snapshots**: daily automatic + manual via console / CLI.

### PITR command (when needed)

```bash
# Restore to a point in time (10 minutes ago)
aws rds restore-db-instance-to-point-in-time \
    --source-db-instance-identifier anime-prod \
    --target-db-instance-identifier anime-prod-pitr-$(date +%s) \
    --restore-time $(date -u -d '10 minutes ago' --iso-8601=seconds)

# Or restore from a named snapshot
aws rds restore-db-instance-from-db-snapshot \
    --db-snapshot-identifier <snap-id> \
    --db-instance-identifier anime-prod-restored
```

Then point the app at the restored instance — see
`docs/runbooks/db-down.md` §3d/§3e for the failover procedure including
the K8s `DATABASE_URL` flip.

### Cloud drill cadence

The cloud-side drill (provision a PITR restore + smoke test it) belongs
in **the staging environment**. Don't drill PITR against prod — drill it
against a staging restore.

---

## 4. Backup retention policy

Local dumps are NOT auto-pruned. The dev disk fills up if you forget.

Recommended local hygiene (cron / launchd / scheduled task):

```bash
# Keep last 14 days of local dumps
find backups -name 'anime_*.sql.gz' -mtime +14 -delete
find backups -name 'anime_*.sql.gz.sha256' -mtime +14 -delete
```

Cloud retention is set in the Terraform RDS module (7 days for v1).
Bump to 14 or 30 once compliance posture demands it (see the log
retention policy doc).

---

## 5. RPO / RTO budgets (NFR mapping)

| NFR | Target | How this drill / cloud setup achieves it |
|---|---|---|
| RTO (Recovery Time Objective) | < 30 min | Local: restore from latest dump in <5 min. Cloud: PITR restore in 15–25 min (AWS-managed). |
| RPO (Recovery Point Objective) | < 5 min | Local: drill cadence sets this — run weekly or after schema change. Cloud: continuous PITR within retention window. |

If the local drill ever takes >5 min, the dump size has outgrown the
single-file restore pattern. That's a "schema/data exploded; revisit
backup strategy" signal — could indicate corpus bloat or unbounded
table growth.

---

## 6. Drill history

Run weekly OR after any migration (`alembic upgrade head`) OR after any
ingestion job that materially changes the data shape.

| Date | Operator | Live row count (top-3 tables) | Drill result | Notes |
|---|---|---|---|---|
| _(not yet run — pending `make dev` + ingested corpus)_ | — | — | — | — |

---

## 7. Design rationale

- **Postgres as primary, single instance v1** — this drill is the
  operational proof that single-instance is acceptable: restore works.
- **Failure modes — DB-down is the "hard dependency" path** — the
  drill closes the loop on `docs/runbooks/db-down.md` §3e (PITR procedure
  documented + practiced).

When the drill exposes a gap (e.g. an extension we forgot to enable in
the restore target), fix the dump script + re-run, don't paper over it
in the runbook.
