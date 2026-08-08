# Chaos Procedures

Operating manual for the chaos scripts in `scripts/chaos/`. **"What good
looks like" sections are the load-bearing part of each scenario** — without
concrete expected outputs, a chaos test that "completes" tells you nothing.

All scenarios are paired with `scripts/chaos/restore.sh` (also: `make
chaos-restore`) which idempotently converges the local stack back to a
healthy state. Run it any time you wonder "what state is the stack in?"

## Pre-flight

```bash
# 1. Stack must be up
make dev                                     # OR: docker compose up -d

# 2. K6_AUTH_TOKEN exported (chaos probes send authenticated requests)
export K6_AUTH_TOKEN="<your-clerk-dev-jwt>"  # see tests/load/README.md §2

# 3. Sanity
curl -s http://localhost:8000/ready          # expect {"status":"ready"}
```

If any of these fail, the chaos run won't tell you anything useful — fix
the pre-flight first.

---

## §1 — kill-LLM (`make chaos-llm` / `scripts/chaos/kill_llm.sh`)

### §1a. The scripted scenario: kill-switch path

**Implements:** the cost-control kill switch and its degraded-response path.

**What the script does (literally):**

1. Backs up `.env` → `.env.chaos-backup`.
2. Flips `LLM_ENABLED=false` in `.env`.
3. `docker compose up -d --no-deps --force-recreate api` — api restarts with new env.
4. After ~8s, probes `POST /v1/recommend`.
5. Holds 15s (configurable `--duration`).
6. Trap restores `.env` + force-recreates api.

**What good looks like:**

| Signal | Expected | Where to check |
|---|---|---|
| HTTP status | **503** (NOT 500) | curl output |
| Response body | Contains "temporarily unavailable" or similar | `/tmp/anime_chaos_response.json` |
| Langfuse traces (chaos window) | **Zero** LLM calls during the chaos window | Langfuse UI → Traces, filter by timestamp |
| Structured logs | `event="llm.kill_switch.tripped"` or `LLM_ENABLED=false` boot log | `docker compose logs api --since 1m` |
| After restore | `/v1/recommend` returns 200 within ~10s | Run `make chaos-restore && curl` |

**What BAD looks like:**

- 500 instead of 503 — means the degradation isn't a planned path; the kill switch is buggy.
- 200 returned with real recommendations — the env override didn't take effect. Check that the api was force-recreated, not just restarted.
- Restore left the system broken — `.env.chaos-backup` should be moved back to `.env` AND `api` force-recreated. Re-run `make chaos-restore` manually.

### §1b. The manual procedure: Groq → OpenAI fallback chain

The scripted version (§1a) exercises the kill-switch path. To test the
**fallback chain proper** (Groq fails → OpenAI takes over → response
returns 200), the cleanest path is:

```bash
# 1. Snapshot .env
cp .env .env.chaos-backup

# 2. Invalidate ONLY the Groq key (leave OpenAI intact)
sed -i.bak 's/^GROQ_API_KEY=.*/GROQ_API_KEY=chaos-invalid-key/' .env
docker compose up -d --no-deps --force-recreate api

# 3. Wait + probe
sleep 8
curl -X POST http://localhost:8000/v1/recommend \
    -H "Authorization: Bearer $K6_AUTH_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"query":"fallback chain test"}' | jq

# 4. Restore
mv .env.chaos-backup .env
docker compose up -d --no-deps --force-recreate api
```

**What good looks like (§1b):**

- HTTP 200 returned (OpenAI fallback fires successfully).
- Langfuse trace shows `provider=openai` and the `groq` attempt that
  failed (per the fallback chain).
- API log shows `event="llm.fallback.fired" provider_from="groq" provider_to="openai"`.
- Total latency may exceed the warm-Groq baseline by ~1-2s — that's OK,
  it's the fallback hop.

**If §1b fails (no fallback fires, returns 500 or hangs):** the resilience
layer is misconfigured. See `packages/core/src/anime_core/resilience.py`
and confirm the circuit breaker for `groq` opens after N failures.

---

## §2 — kill-Postgres (`make chaos-pg` / `scripts/chaos/kill_pg.sh`)

**Implements:** the hard-dependency path (accepted) and its graceful 503.

**What the script does:**

1. `docker compose stop postgres`.
2. Waits 6s.
3. Probes `/health` (expect 200), `/ready` (expect 503), `/v1/recommend` (expect 503).
4. Holds for 15s.
5. Trap starts postgres back + verifies `/ready` recovers to 200.

**What good looks like:**

| Signal | Expected | Why |
|---|---|---|
| `/health` | **200 throughout** | Liveness is "process up" — independent of dependency state. K8s should NOT restart this pod. |
| `/ready` | **503 within ~6s** | Readiness checks DB — LB pulls the pod, but the pod stays alive waiting for DB recovery. |
| `/v1/recommend` | **503 friendly** | DB is required for ACL + query history; degraded path is the documented behavior. |
| After restore | `/ready` → 200 within ~10s | Postgres warm-up is fast. |
| Postgres data | **Intact** | This is chaos, not data destruction. Volume mount persists. |

**What BAD looks like:**

- `/health` flips to 503 too. Means liveness probe is wrong — should NOT check DB. Fix: see `apps/api/src/anime_api/routes/health.py`.
- `/v1/recommend` returns 500. Means there's no try/except around the DB call — the fallback is missing.

---

## §3 — Net-partition (`make chaos-net` / `scripts/chaos/net_partition.sh`)

**Implements:** the cache-as-degradation path (not a hard requirement).

**What the script does:**

1. `docker network disconnect <project>_default <api-container>` — partitions api from BOTH redis and postgres (everything on the same docker network).
2. Waits 5s.
3. Probes `/v1/recommend`.
4. Holds 15s.
5. Reconnects.

Defaults to `--target redis` semantically (the probe expectation is "cache
miss + correctness preserved"). The actual partition affects all
co-networked containers — concrete enough for v1.

**What good looks like (--target redis):**

| Signal | Expected |
|---|---|
| `/v1/recommend` | **200** (correctness preserved — Redis is non-critical) |
| Response latency | Higher than warm-cache baseline (no semantic-cache hit) |
| API logs | `event="circuit_breaker.open" target="redis"` after N failures |
| After restore | First request hits Redis fresh; cache warms back up |

**What good looks like (--target llm):**

- HTTP 503 friendly returned within ~10s (no infinite hang).
- Resilience layer should detect the LLM circuit broke open and short-
  circuit, not retry forever.

**What BAD looks like:**

- Request hangs > 30s. Circuit breakers aren't engaging — the timeout
  hierarchy in `resilience.py` is the place to fix.
- 500 instead of 503. Same bug class as §2: unhandled exception path.

---

## §4 — Restore (`make chaos-restore` / `scripts/chaos/restore.sh`)

**Always idempotent. Always safe to run.**

The restore script does NOT need to know what was last broken. It
converges the local stack to a healthy state regardless of starting
condition:

1. Restore `.env` from `.env.chaos-backup` if present.
2. `docker compose up -d --no-deps postgres redis api` (ensures all up).
3. Reconnect api to compose network (no-op if already connected).
4. Poll `/ready` until 200 or 30s timeout.

If step 4 fails: check `docker compose ps`, `docker compose logs api
--tail 50`, and `docker network ls`. The script will exit non-zero so a
wrapping CI job can detect the failure.

---

## Cadence + history

Run these scenarios:
- **Each change** that touches resilience.py, the LLM
  client, the cache layer, or the readiness probe — to confirm the chaos
  paths still hold.
- **Quarterly** as part of the runbook freshness review.
- **After any Dependabot batch** that bumps `pybreaker`, `redis`, `httpx`,
  `sqlalchemy`, or `langchain*`.

Record run history below so the next person knows when this was last
verified.

| Date | Scenario | Operator | Result |
|---|---|---|---|
| _(not yet run — pending `make dev` + K6_AUTH_TOKEN)_ | — | — | — |

---

## Related procedures

These procedures provide operational proof for:
- **LLM tiering + fallback chain** — §1b
- **Cost-control kill switch** — §1a
- **Failure-mode + degradation per component** — §1, §2, §3
- **Redis as a cost-not-correctness layer** — §3
- **Postgres as a hard dependency** — §2

When the chaos paths don't match the docs, that's the runbooks' problem,
not chaos's problem — fix the runbook, then re-run the chaos to confirm.
