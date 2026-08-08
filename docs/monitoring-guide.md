# Monitoring Guide — watching a single query through every tool

**Scenario:** you just typed a query into the web app at <http://localhost:1006>.
This guide shows you how to find *that exact query* in every tool, what a HEALTHY
signal looks like, and what a PROBLEM looks like.

All ports come from `.env`; run `make urls` to print them. Defaults used below:

| Tool | URL | Login |
|---|---|---|
| Web app | <http://localhost:1006> | Clerk |
| API / Swagger | <http://localhost:1005/docs> | — |
| **Langfuse** (LLM traces) | <http://localhost:1013> | `admin@anime.local` / `anime-admin-1234` |
| **Grafana** | <http://localhost:1019> | `admin` / `admin` |
| **Prometheus** | <http://localhost:1018> | — |
| RedisInsight | <http://localhost:1016> | — |
| Postgres | `localhost:1002` db=`anime` user=`anime` pw=`anime` | — |
| LocalStack SQS | <http://localhost:1004> | — |

---

## 0. The one thing that ties it all together: the correlation ID

Every response carries an `x-request-id`, and every log line + trace carries a
matching `trace_id`. **Grab it first — it unlocks every other tool.**

```bash
curl -s -D - -o /dev/null -X POST http://localhost:1005/v1/recommend \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"query":"a psychological thriller with an unreliable narrator"}' \
  | grep -i x-request-id
# x-request-id: 0353698a37c345b6b4d6fbceadee7e6f
```

Then get its `trace_id` from the logs:

```bash
docker logs anime-api 2>&1 | grep 0353698a37c345b6b4d6fbceadee7e6f | head -1
# {"event": "request.start", "request_id": "0353698a...", "trace_id": "e1cc3b91b415a0754f6c2c5b660aef54", ...}
```

That `trace_id` is the **same ID in Langfuse**. This is the demo money-shot.

---

## 1. Logs (structured JSON)

**Find your request:**
```bash
docker logs anime-api 2>&1 | grep "<request_id>"
```

**Pretty-print just the useful fields:**
```bash
docker logs anime-api 2>&1 | grep "<request_id>" | \
  python -c "import sys,json;[print(json.loads(l).get('event'), json.loads(l).get('trace_id')) for l in sys.stdin]"
```

**HEALTHY:**
- `request.start` → `request.end` with `status_code: 200`
- Every line has `request_id`, `trace_id`, `span_id`, ISO-8601 UTC `timestamp`
- **No `email` and no `query` text anywhere** (PII redaction working)

**PROBLEM:**
- `reranker failed/timed out; falling back to hybrid order` ← **currently fires on every cache-miss** (known issue)
- `usage model ... has no pricing entry` ← **cost is being recorded as $0** (known issue)
- `primary LLM ... raised (...); falling back to gpt-4o-mini` ← Groq is down; fallback engaged (this is *working as designed*, but investigate Groq)
- `all LLM tiers failed; serving popular fallback` ← both providers dead
- Any raw email address or query text ← PII leak, treat as an incident

---

## 2. Langfuse — the LLM trace (prompt, model, tokens, cost, latency)

**Open:** <http://localhost:1013> → log in → your project → **Tracing → Traces**

**Find your query:**
- Filter by name `POST /v1/recommend` (the list is dominated by `GET /health` noise — see M1)
- Or paste the `trace_id` directly into the URL: `http://localhost:1013/project/<id>/traces/<trace_id>`

**What to look at, in order:**
1. **Trace latency** (top of page). Healthy cold: 3–5s. Cached: < 100ms.
2. **The span tree** (26 spans for a full query). Expand it and read top-down:
   - `POST /v1/recommend` — the root; total wall time
   - `POST` (httpx) — the **OpenAI embedding** call (~300ms healthy; >1s = network/RTT problem)
   - `GENERATION ChatGroq` — **the LLM call**. Click it.
   - `GET` / `SET` / `INCRBY EXPIRE` / `LPUSH LTRIM` — Redis cache + quota ops (sub-ms)
   - `connect` — Postgres
3. **Click the `GENERATION` span** — this is the money panel:
   - **Input** — the full rendered prompt (system + retrieved CANDIDATES + user query)
   - **Output** — the raw structured output
   - **Model** — should be `openai/gpt-oss-20b`
   - **Tokens** — e.g. `in=922 out=798`
   - **Cost** — ⚠️ **currently always `0`** (C2: model missing from pricing table)

**HEALTHY:** one `GENERATION` per query; tokens present; latency ~1.5s; prompt contains the retrieved candidates.

**PROBLEM:**
- **Two `GENERATION` spans** → the primary tier failed and it fell back (check the model names)
- `in` tokens climbing over time → context is growing; check `MAX_CANDIDATE_CHARS`
- **Cost = 0** → pricing table gap (add the model in Langfuse *Settings → Models* AND in `cost_meter.py`)
- **~2s gap in the span tree with no child span** → that's the **reranker timing out** (it isn't instrumented). This is C1.

---

## 3. Grafana / Prometheus — ⚠️ read this before you trust it

**Honest status: the metrics pipeline carries ZERO application metrics.**

- Prometheus (<http://localhost:1018>) → **Status → Targets** → both targets show `UP`
- But: `Graph` → run `http_server_duration_milliseconds_count` → **0 series**
- Grafana's "API Overview" dashboard has one panel literally titled *"HTTP server request rate (if instrumented)"* → **No data**

**Why:** [`otel.py`](../packages/core/src/anime_core/observability/otel.py) configures a
**TracerProvider only** — there is no `MeterProvider` and no counter/histogram instrumentation
anywhere in the codebase. Traces work; metrics do not exist.

**The only PromQL that works today:**
```promql
up                       # 1 = the scrape target is alive (2 series)
```

**App-metric panels are not wired yet** — the app emits traces and logs but no
metrics (there's no `MeterProvider`). Once one is added, these are the queries
to use:
```promql
sum(rate(http_server_duration_milliseconds_count[1m])) by (http_route)   # RPS by route
histogram_quantile(0.95, sum(rate(http_server_duration_milliseconds_bucket[5m])) by (le))  # p95
sum(rate(llm_cost_usd_total[5m]))                                        # $/sec
```

---

## 4. OTel traces — finding the slow hop

The collector receives spans and forwards them to Langfuse, so **Langfuse *is* your span viewer**
(section 2). To confirm the collector itself is receiving:

```bash
docker logs anime-otel-collector 2>&1 | tail -5      # should show batches being exported
curl -s http://localhost:1017/metrics | head          # ⚠️ currently EMPTY (C5)
```

**How to find the slow hop:** in the Langfuse span tree, sort by duration. Today the pattern is:
```
POST /v1/recommend          5.1s   ← total
├─ POST (embedding)         1.5s   ← OpenAI RTT
├─ GENERATION ChatGroq      1.5s   ← the LLM
└─ [~2.1s UNACCOUNTED]             ← the reranker timing out (not instrumented!)
```
That unaccounted gap **is** the bug. Any span tree where children don't sum to the parent means
something un-instrumented is eating time.

---

## 5. Postgres — the durable record

```bash
docker exec -it anime-postgres psql -U anime -d anime
```

**Your query in history:**
```sql
SELECT id, user_id, query, created_at
FROM query_history ORDER BY id DESC LIMIT 5;
```

**The cost of your query:**
```sql
SELECT user_id, day, query_count, input_tokens, output_tokens, cost_usd
FROM usage_daily WHERE day = CURRENT_DATE;
```
**HEALTHY:** `query_count` increments; `input_tokens`/`output_tokens` > 0; `cost_usd` > 0.
**PROBLEM (current):** `input_tokens=0, output_tokens=0, cost_usd=0.000000` ← C2.

**Your feedback:**
```sql
SELECT id, user_id, query_history_id, mal_id, rating, created_at
FROM feedback ORDER BY id DESC LIMIT 5;
```

**Corpus + vector sanity:**
```sql
SELECT embedding_model, vector_dims(embedding), count(*) FROM anime_chunks GROUP BY 1,2;
-- text-embedding-3-small | 1536 | 269

EXPLAIN ANALYZE SELECT id FROM anime_chunks
ORDER BY embedding <=> (SELECT embedding FROM anime_chunks LIMIT 1) LIMIT 20;
-- PROBLEM: "Seq Scan" ← no HNSW index (H1). Healthy would say "Index Scan using ... hnsw".
```

---

## 6. Redis — caches, quota, dedup

GUI: <http://localhost:1016> (RedisInsight, both Redis instances pre-added). Or CLI:

```bash
docker exec anime-redis redis-cli --scan | sed 's/:[^:]*$/:*/' | sort | uniq -c
#   17 embed:*            ← embedding cache
#   16 resp:v1:anon:*     ← response cache (exact query)
#    1 sem:v1:*           ← semantic cache (ONE list key per tenant)
#    1 quota:<user>:*     ← daily quota counter
```

**Prove a cache hit (the best cheap demo):**
```bash
# run the same query twice — second one is ~200x faster
time curl -s -o /dev/null -X POST .../v1/recommend -d '{"query":"same query"}'   # ~4s  (cold)
time curl -s -o /dev/null -X POST .../v1/recommend -d '{"query":"same query"}'   # ~0.02s (HIT)
```

**Quota counter:**
```bash
docker exec anime-redis redis-cli GET "quota:<user_id>:$(date -u +%F)"   # e.g. 24 (limit 100)
```

**Semantic cache depth:**
```bash
docker exec anime-redis redis-cli LLEN "sem:v1:anon"    # 13
```
⚠️ **PROBLEM:** at `SEMANTIC_CACHE_THRESHOLD=0.92`, genuine paraphrases score 0.62–0.85 and **miss**.
The semantic cache almost never fires (H2).

**Worker eval signals:**
```bash
docker exec anime-redis redis-cli GET eval:feedback_count            # 1
docker exec anime-redis redis-cli LRANGE eval:review_queue 0 -1      # thumbs-down samples
docker exec anime-redis redis-cli --scan --pattern 'seen:*'          # idempotency dedup keys
```

---

## 7. SQS — the async path (feedback → worker)

```bash
Q=http://localhost:4566/000000000000/anime-dev-feedback

# queues (3 main + 3 DLQ)
docker exec anime-localstack awslocal sqs list-queues

# depth (visible + in-flight)
docker exec anime-localstack awslocal sqs get-queue-attributes --queue-url $Q \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible

# DLQ depth  ← the number you actually alert on
docker exec anime-localstack awslocal sqs get-queue-attributes --queue-url ${Q}-dlq \
  --attribute-names ApproximateNumberOfMessages

# redrive policy
docker exec anime-localstack awslocal sqs get-queue-attributes --queue-url $Q \
  --attribute-names RedrivePolicy        # maxReceiveCount: 5
```

**Watch the worker consume, live:**
```bash
docker logs -f anime-worker
# {"event": "worker polling anime-dev-feedback", ...}
# {"event": "queued thumbs-down for eval review: mal_id=19", ...}
# {"event": "duplicate job feedback:1 (feedback.recorded); skipping", ...}   ← idempotency
```

**HEALTHY:** main-queue depth ~0; DLQ **0**; worker `RestartCount` stable.
**PROBLEM:**
- **DLQ > 0** → poison messages. Inspect them, then purge.
- **Worker `RestartCount` climbing** → ⚠️ **C3: a malformed message crash-loops the worker.**
  ```bash
  docker inspect anime-worker --format '{{.RestartCount}}'
  ```
  Any non-zero growth here is an incident until C3 is fixed.

---

## 8. The 60-second health sweep

```bash
make ps                                                   # all 16 up?
curl -s localhost:1005/health && curl -s localhost:1005/ready
docker inspect anime-worker --format '{{.RestartCount}}'  # should be stable
docker exec anime-localstack awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/anime-dev-feedback-dlq \
  --attribute-names ApproximateNumberOfMessages           # should be 0
docker logs anime-api 2>&1 | grep -c "reranker failed"    # should be 0 (currently: NOT)
docker exec anime-postgres psql -U anime -d anime -tAc \
  "SELECT sum(cost_usd) FROM usage_daily WHERE day=CURRENT_DATE"   # should be > 0 (currently: 0)
```
