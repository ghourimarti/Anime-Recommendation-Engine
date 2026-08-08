# Stage 1: Local Docker

The first deployment stage. Proves that the system works end-to-end inside
containers, restored from a cold start. NOT "my Python venv runs the API
while compose runs Postgres" — ALL services in containers.

**Implements:** the local-Docker deployment gate; cross-refs the Docker
artifacts and the backup drill.

---

## 1. What Stage 1 proves (and what it doesn't)

| Proves | Doesn't prove |
|---|---|
| Image builds are reproducible | K8s manifests are correct (Stage 2) |
| Container DNS works (svc names resolve) | Cloud IAM / VPC / security groups (Stage 3-4) |
| env_file handling is correct | Scale behavior at NFR target (Stage 5) |
| Healthchecks fire at sane intervals | Real-user traffic patterns (Stage 6) |
| Volumes mount with correct perms | RDS-specific behavior (Stage 4) |
| Backup format + restore path work | Real cost behavior |
| Full e2e flow (auth → query → cache → LLM → DB) is wired | … |

If Stage 1 passes, none of the above failure classes will surprise you in
Stage 2. If Stage 1 fails, EVERY subsequent stage inherits the bug.

---

## 2. Pre-flight

Confirm before the first cold-start:

```bash
# Tooling
docker --version            # 20.10+
docker compose version      # v2.x
curl --version              # any
jq --version                # optional; nicer output

# Env
cat .env | grep -E '^(GROQ_API_KEY|OPENAI_API_KEY|CLERK_SECRET_KEY|NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)='
# All four MUST be set for the full e2e flow.

# Clerk dev JWT (for the auth-path probe in §4.2)
echo "$K6_AUTH_TOKEN" | head -c 30   # if empty: see tests/load/README.md §2
```

If any check fails, fix it before running the acceptance — Stage 1 is
not the place to discover missing keys.

---

## 3. The acceptance sequence

Run in this order. Each step must pass before the next is meaningful.

### 3.1 Cold start

```bash
# Critical: -v wipes volumes, so the next `up` is genuinely cold.
docker compose down -v

# Bring the stack up. The first run takes ~2-3 min (image pulls + builds).
docker compose up -d

# Wait for healthchecks. Watch until all services report (healthy):
docker compose ps
```

**Gate:** `docker compose ps` shows every service `(healthy)` within ~60s
(API + worker may take longer on the first build). If any service shows
`(unhealthy)` or `restarting`, dump its logs (`docker compose logs <svc>`)
and fix BEFORE proceeding. A "mostly healthy" stack masks bugs.

### 3.2 Apply DB migrations + ingest corpus (one-time per cold start)

```bash
make db-migrate                    # applies alembic to head (incl. 0004_account_deletions)
make ingest                        # ~$0.01 OpenAI; populates anime_titles + anime_chunks
```

**Gate:** `make ingest` exits 0 + Postgres shows ~268 rows in
`anime_titles`. If embedding cost shows much higher than ~$0.01, you may
be re-embedding due to a model mismatch — check `.env`.

### 3.3 Bash smoke (acceptance probe)

```bash
export K6_AUTH_TOKEN="<your-clerk-dev-jwt>"   # see tests/load/README.md §2
make deploy-stage1-smoke
```

**Gate:** Script prints `Stage 1 smoke: PASS`. Specifically:

| Probe | Expected |
|---|---|
| `GET /health` | 200 |
| `GET /ready` | 200 |
| 10 × `POST /v1/recommend` | all 200 |
| `/v1/recommend` p95 | < 8000 ms (warm cache; the first call may be higher — see §6) |

Without `K6_AUTH_TOKEN`, the script exits 2 with a warning. That's a
coverage gap, not a pass.

### 3.4 (Recommended) k6 smoke for larger-N percentiles

```bash
make load-smoke                    # 1 RPS for 60s
```

**Gate:** k6 thresholds green (http_req_failed < 5%, p95 budgets met).
The bash smoke (§3.3) proves correctness on a small N; k6 gives you the
percentile distribution.

### 3.5 Backup drill

```bash
make backup-drill                  # local backup + restore drill
```

**Gate:** `[drill] PASS — backup + restore cycle succeeded end-to-end.`
This is the cheapest possible venue to exercise the drill — if it fails
here, it fails in Stage 4 against real RDS too. Drift catches at this
stage are free.

### 3.6 Cleanup

```bash
docker compose down                # leaves volumes intact for the next iteration
# OR
docker compose down -v             # full cold reset (use before the next acceptance)
```

---

## 4. Acceptance gate (single pane of glass)

Stage 1 PASSES iff all of the following are true:

- [ ] §3.1 cold start: all services `(healthy)` within ~60s of `up`
- [ ] §3.2 migrations + ingest: alembic at `0004_account_deletions`, ~268 anime rows
- [ ] §3.3 bash smoke: `Stage 1 smoke: PASS`, p95 < 8000ms
- [ ] §3.4 k6 smoke: thresholds green (optional but strongly recommended)
- [ ] §3.5 backup drill: `[drill] PASS`
- [ ] §3.6 cleanup: `docker compose down -v` returns to clean slate (next `up` is cold)

Any one failing means Stage 1 has NOT passed. Document the failure in §7
(History) and fix before re-running.

---

## 5. Rollback

Stage 1 has the cheapest rollback in the entire deployment sequence:

```bash
docker compose down -v
```

Wipes volumes, kills containers, returns to clean slate. No cloud cost,
no data loss outside the dev box, no operator coordination required.
This is why we drill so much HERE: the cost of a rollback is ~zero.

---

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker compose ps` shows api `(unhealthy)` | DB not ready when api booted | Wait 30s; if persistent, check `docker compose logs postgres` for migration errors |
| `make db-migrate` exits non-zero with "extension vector does not exist" | Postgres image without pgvector | Confirm `pgvector/pgvector:pg16` in docker-compose.yml |
| `make ingest` 401 on OpenAI | Stale `OPENAI_API_KEY` in `.env` | Rotate key in Clerk + Clerk dashboard; rebuild compose env |
| Bash smoke: liveness OK but `/v1/recommend` 401 | `K6_AUTH_TOKEN` expired (Clerk tokens last ~1h by default) | Re-mint per tests/load/README.md §2 |
| `/v1/recommend` p95 wildly high (10s+) on first call | Cold caches; reranker model loading | Run once to warm; subsequent calls reflect warm-state p95 |
| Backup drill MISMATCH on row counts | Schema migration didn't apply in restored container | Check that 0004 migration shipped in the dump |
| `docker compose down -v` doesn't remove volume | Another compose project holds the volume | `docker volume ls`; `docker volume rm <name>` explicitly |

---

## 7. Stage 1 history

Run before promoting to Stage 2. Record the outcome here so the next
operator (or future you) can see when Stage 1 was last verified clean.

| Date | Operator | Result | Notes |
|---|---|---|---|
| _(not yet run)_ | — | — | — |

---

## 8. What unlocks for Stage 2

A passing Stage 1 means:

- **Container build correctness** is no longer a risk for Stage 2.
- **Env-var handling, healthcheck timing, volume mounts** are all known good.
- **Backup format compatibility** is proven (cheap drill = real proof).
- **The Helm chart's app code + image references** are correct, because Stage 2
  uses the same images.

What Stage 2 introduces (and Stage 1 cannot prove):

- Helm rendering correctness
- K8s probe timing under kubelet (vs Docker's healthcheck)
- ConfigMap + Secret mechanics (env_file → K8s Secret swap)
- Service DNS (compose's `postgres` → K8s's `postgres.anime-dev.svc.cluster.local`)
- HPA reactions
- `ImagePullPolicy` semantics

See `docs/deploy/stage2-local-k8s.md` (to be authored when Stage 2 opens).
