# Load Test Scenarios + Tuning Playbook

Five scenarios. Each validates a specific non-functional requirement or feeds a
tuning loop. The tuning playbook (§7) documents how to read the results and act
on them.

## 1. `smoke.js` — 1 RPS, 60s

**Purpose:** prove the harness is wired before burning 5 minutes of OpenAI
spend on a misconfigured run.

**What it catches in ≤60s:**
- Missing `K6_AUTH_TOKEN` env (all `/v1/recommend` return 401)
- Wrong `BASE_URL` (connection refused / DNS)
- Expired Clerk JWT (401 with Clerk error body)
- API not up (`/health` connection refused)
- DB / Redis down (`/ready` returns 503)

**Thresholds** (generous — proving wiring, not performance):
- `http_req_failed < 5%`
- `http_req_duration{name:health} p95 < 200ms`
- `http_req_duration{name:ready} p95 < 1000ms`

**Run:**
```bash
k6 run -e BASE_URL=http://localhost:8000 -e K6_AUTH_TOKEN=$TOKEN tests/load/k6/smoke.js
```

---

## 2. `sustained_50rps.js` — 50 RPS, 5 min

**Purpose:** THE NFR-validating scenario. 50 RPS sustained = the
"designed-for" sustained rate. If this fails, the architecture doesn't meet
its documented target — go to §7's tuning playbook.

**Thresholds map 1:1 to the NFRs:**
| Threshold | NFR |
|---|---|
| `http_req_failed < 1%` | Uptime SLO 99.5% (load-test surrogate) |
| `http_req_duration p50 < 3000` | Full response p50 < 3s |
| `http_req_duration p95 < 8000` | Full response p95 < 8s |
| `http_req_duration p99 < 15000` | Tail-latency budget |
| `anime_server_work_ms p95 < 7500` | Server-side ≤ p95 budget minus network |

**Run:**
```bash
k6 run -e BASE_URL=http://localhost:8000 -e K6_AUTH_TOKEN=$TOKEN \
  --summary-export=tests/load/reports/sustained_50rps_$(date +%s).json \
  tests/load/k6/sustained_50rps.js
```

---

## 3. `peak_200rps.js` — 200 RPS, 90s

**Purpose:** burst-headroom validation. NFR: designed-for peak ≈ 200 RPS.
If the system can't hold 200 RPS for 90s, autoscaling never engages in prod.

**Thresholds** (relaxed vs sustained — peak tolerates tail growth):
- `http_req_failed < 2%`
- `http_req_duration p95 < 15000`
- `http_req_duration p99 < 30000`
- `anime_server_work_ms p95 < 14000`

**Run:** same shape as sustained, change the script + report name.

---

## 4. `ramp_to_knee.js` — 10 → 500 RPS over 10 min

**Purpose:** find the knee. Diagnostic only — **no thresholds** by design.
Use when sustained_50rps regresses unexpectedly: ramp finds the new
breaking point, the playbook tells you which knob to turn.

**How to read the result:** plot p95 vs RPS (k6 `--summary-export` JSON has
the percentiles per stage). The inflection point is the knee. Apply the
playbook from §7 starting at the cheapest-to-tune layer.

---

## 5. `stream_sustained_30rps.js` — 30 RPS, 3 min (xk6-sse REQUIRED)

**Purpose:** TTFT validation for the streaming endpoint. NFR target:
TTFT p50 < 800ms, p95 < 2.5s, p99 < 5s.

**Why 30 RPS (not 50):** streaming holds the SSE connection open ~3–8s.
At 50 RPS × 5s mean = 250 concurrent connections. 30 RPS is the comfortable
"demonstrate the pattern works" rate for local docker-compose.

**Custom k6 binary required** — see [README.md §4](README.md) for the build
procedure (Docker image or local Go install).

**Thresholds:**
- `anime_sse_ttft_ms p50 < 800` (TTFT p50 NFR)
- `anime_sse_ttft_ms p95 < 2500` (TTFT p95 NFR)
- `anime_sse_ttft_ms p99 < 5000` (TTFT p99 NFR)
- `anime_sse_total_ms p95 < 8000`
- `anime_sse_connect_errors < 10`

---

## 6. Recommended run order

```
1. smoke.js                  ← Always first. <2 min including warm-up.
2. sustained_50rps.js        ← The NFR gate. If green, move on.
3. peak_200rps.js            ← Headroom. Run after sustained is green.
4. stream_sustained_30rps.js ← Streaming TTFT. Needs custom k6 binary.
5. ramp_to_knee.js           ← Diagnostic. Run when something regresses.
```

---

## 7. Tuning playbook — bottleneck order

When a scenario fails its threshold, turn knobs in this order (cheapest first):

### Tier 1 — Caching (cheapest, biggest lever)

**Symptom:** sustained_50rps p95 > 8s, server_work_ms p95 high, but error rate low.

| Knob | Where | Effect | When |
|---|---|---|---|
| `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` 0.92 → 0.88 | `.env` / Helm values | Looser semantic-cache hits → fewer LLM calls | When real distinct queries are <60% of mix |
| `RESPONSE_CACHE_TTL_SECONDS` 86400 → 604800 | `.env` | Hot-keys hit cache longer | Stable corpus, no per-user personalization |
| `EMBEDDING_CACHE_TTL_SECONDS` ∞ (default) | n/a | Already optimal | — |

**Re-run:** smoke + sustained_50rps. Expect p95 to drop by 30-60% if cache hit rate climbs.

### Tier 2 — Retrieval

**Symptom:** server_work_ms p95 high AND cache hit rate already ≥ 30%.

| Knob | Where | Effect | When |
|---|---|---|---|
| `RETRIEVAL_TOP_K` 20 → 10 | `.env` | Fewer candidates → faster pgvector + reranker | If recall@3 unchanged in eval (run `make eval-compare`) |
| `RERANKER_BATCH_SIZE` 32 → 64 | `.env` | Bigger batches → fewer model calls | If CPU has headroom |
| `RERANK_K` 5 → 3 | `.env` | Fewer reranker scores | If MMR pre-filter is good enough |

**Re-run:** `make eval` first to confirm quality isn't sacrificed; then sustained_50rps.

### Tier 3 — LLM

**Symptom:** server_work_ms p95 dominated by generation; retrieval p95 < 300ms.

| Knob | Where | Effect | When |
|---|---|---|---|
| Default model: 8B → smaller variant (if available) | `.env` `LLM_DEFAULT_MODEL` | Fewer tokens/sec needed | If quality eval (RAGAS) stays within 3% |
| `LLM_MAX_OUTPUT_TOKENS` 800 → 600 | `.env` | Shorter generations → faster | If recommendations are verbose; cross-check user feedback |
| Route MORE queries to escalation tier | tier logic | Improves quality, increases cost | Inverse of above: when quality is the bottleneck, not latency |

**Re-run:** `make eval` (quality must hold) + sustained_50rps.

### Tier 4 — Postgres / connection pool

**Symptom:** error rate >1% under sustained, `http_req_failed` shows 5xx; cache + retrieval already tuned.

| Knob | Where | Effect | When |
|---|---|---|---|
| `DB_POOL_SIZE` 10 → 30 | `.env` | Fewer connection-acquire timeouts | High concurrency + small pool |
| `DB_POOL_MAX_OVERFLOW` 5 → 15 | `.env` | Burst headroom | Spiky workload |
| Add read replica | Terraform | Reads spread across nodes | After vertical scaling is maxed |

**Re-run:** sustained_50rps. Expect error rate to drop to <0.5%.

### Tier 5 — Vector DB (pgvector / Qdrant flip)

**Symptom:** retrieval p95 > 200ms after T1-T4 tuning; ramp_to_knee inflects below 100 RPS.

This is the documented trigger to revisit the vector-DB choice. Don't tune your
way through it — escalate to a vector-DB swap (Qdrant + a sidecar deployment).
See `docs/runbooks/db-down.md` §3 for the migration shape.

---

## 8. What "passing" really means

A passing scenario proves the **patterns** hold under synthetic load on a local
docker-compose stack with a single API replica. It does NOT prove:

- Production at 100k MAU is operationally healthy (needs real users + on-call)
- Long-tail failure modes (the 11-day memory leak; cache stampede on a single
  hot key; per-tenant runaway query) — only real traffic surfaces these
- Multi-region / cross-AZ latency behavior — needs the cloud deployment

Synthetic load demonstrates the *patterns*; operating at scale (real traffic,
on-call, multi-region) is a separate concern this repo does not claim to prove.

---

## 9. Deferred scenarios (v1.x)

- **Soak** (25 RPS for 30 min): memory-leak detection. Deferred in v1; add when
  the first long-running prod deploy ships.
- **Multi-tenant fairness**: hot-tenant doesn't degrade cold-tenant p95. Needs
  the tenancy layer wired further than v1; add in a later hardening pass.
- **Cost-spike repro**: deliberately hit the kill-switch path under load. Lives
  in `docs/runbooks/cost-spike.md` as a manual chaos exercise instead.
