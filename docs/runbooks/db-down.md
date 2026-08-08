# Runbook — Postgres Unreachable

Postgres is a hard dependency (auth lookups, ACL, query history, quota counter,
pgvector). If it's unreachable, the app correctly returns 503; this runbook
gets it back.

**Severity:** P1 — user-visible 503s.

---

## 1. Symptoms

- API logs: `event="db.connection.timeout"` or `event="db.connection.refused"`.
- `/ready` returns 503 (the readiness probe checks DB); LB pulls pods.
- `/health` may still return 200 (liveness probe — process is alive, no
  DB check) → K8s does NOT restart pods, correctly waiting for the DB.
- Grafana dashboard "API latency" shows error rate spike + zero traffic to
  retrieval (because the API short-circuits at the dependency).

---

## 2. Triage — what kind of "down"?

```bash
# 1. Is the RDS instance responding at all?
aws rds describe-db-instances --db-instance-identifier anime-prod \
  --query 'DBInstances[0].DBInstanceStatus'
# Expected: "available". Other values: "modifying", "failed", "maintenance".

# 2. Is the failover replica healthy?
aws rds describe-db-instances --db-instance-identifier anime-prod-replica \
  --query 'DBInstances[0].DBInstanceStatus'

# 3. Can you reach the writer from a debug pod?
kubectl run -it --rm pg-debug --image=postgres:16 -n anime-prod -- \
  psql "postgresql://anime:$(kubectl get secret anime-db -o jsonpath='{.data.password}' | base64 -d)@anime-prod.<rds-host>:5432/anime" -c 'SELECT 1;'
```

| Result | Likely cause | Go to |
|---|---|---|
| `available` AND debug psql works | Network / security group | §3a |
| `available` AND debug psql times out | RDS connection limit reached | §3b |
| `modifying` / `maintenance` | Scheduled maintenance — AWS owns this | §3c |
| `failed` | RDS instance failure | §3d (restore from replica) |
| Cannot describe instance | IAM / network outage | §3e |

---

## 3. Mitigations

### 3a. Network / security group regression

Check whether a recent infra change tightened security groups:
```bash
cd infra/terraform/envs/prod
terraform state list | grep security_group
terraform show <rds-sg-resource>
```

Confirm port 5432 is open from the EKS node group SG. If a recent PR removed
that rule, revert and re-apply.

### 3b. Connection-limit exhaustion

The application has a connection pool (`DB_POOL_SIZE` default 10). If the
pool keeps growing, the RDS `max_connections` ceiling hits.

```bash
# Current connection count from RDS Performance Insights
aws cloudwatch get-metric-statistics --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=anime-prod \
  --statistics Average --period 60 --start-time $(date -u -d '15 minutes ago' --iso-8601=seconds) \
  --end-time $(date -u --iso-8601=seconds)
```

Mitigation: temporarily reduce pod count (autoscale to 1) until the connection
count drops, then root-cause why pool size grew.

### 3c. Maintenance window

If you didn't schedule this, change your maintenance window — AWS chose it.

```bash
aws rds modify-db-instance --db-instance-identifier anime-prod \
  --preferred-maintenance-window sun:04:00-sun:05:00
```

For the duration: the readiness probe correctly pulls pods, user-visible
behavior is "service temporarily unavailable." Nothing to do operationally
except wait + monitor.

### 3d. RDS instance failure → failover

If you have a Multi-AZ deployment (the Terraform default), AWS triggers
failover automatically (≤2 min). If you have a manual read-replica:

```bash
# Promote the replica
aws rds promote-read-replica --db-instance-identifier anime-prod-replica

# Update the K8s secret with the new writer endpoint
kubectl set env deploy/anime-api \
  DATABASE_URL="postgresql+asyncpg://anime:$(kubectl get secret anime-db -o jsonpath='{.data.password}' | base64 -d)@anime-prod-replica.<rds-host>:5432/anime" \
  -n anime-prod
kubectl rollout restart deploy/anime-api -n anime-prod
```

### 3e. PITR — accidental data damage

If the issue is bad data (a migration corrupted rows, a user deletion went
sideways), use Point-in-Time Recovery:

```bash
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier anime-prod \
  --target-db-instance-identifier anime-prod-pitr \
  --restore-time $(date -u -d '10 minutes ago' --iso-8601=seconds)

# Wait for it to come up, then point the app at the new instance
# (same as §3d but with the PITR endpoint).
```

PITR window: 7 days (RDS default). RPO: < 5 min (NFR).

---

## 4. Degradation behavior reminder

While Postgres is unreachable, the app DOES NOT serve recommendations
(retrieval needs pgvector, which lives in Postgres). The fallback chain
returns:

1. `/v1/recommend` → 503 with a friendly "service temporarily unavailable" message.
2. `/health` → 200 (process is alive).
3. `/ready` → 503 (the LB pulls the pod, but K8s doesn't restart it).
4. `/v1/recommend/stream` → SSE connection closes with an error event.

The Next.js frontend renders a "we're having trouble — try again shortly"
state (the streaming UX includes this case).

---

## 5. Post-incident

1. RTO: how long from alert-fire to first 200 OK? Target < 30 min (NFR).
2. RPO: how much data was lost? Target < 5 min (NFR). If exceeded, that's
   a real finding.
3. Backup/restore drill: when did you last successfully run §3e PITR
   as a test? If > 90 days, schedule a chaos test.

---

## 6. Design rationale

Implements the operational discipline behind:
- **Postgres as primary** — single instance v1, with a read-replica v1.x trigger.
- **AWS RDS managed**
- **Failure modes** — DB-down is the "hard dependency" path.

---

**3 a.m. review:** 2026-06-12, Zaini — verified the §3e PITR command syntax
against current AWS CLI (`restore-db-instance-to-point-in-time` still valid).
Cross-referenced the local-mirror procedure at `docs/hardening/chaos-procedures.md §2`
+ the operational drill in `docs/hardening/backup-restore-drill.md`. The
triage table (§2) is what makes this runbook usable at 3 a.m. — DO NOT skip.
