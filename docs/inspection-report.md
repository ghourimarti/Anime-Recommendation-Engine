# Full-System Inspection Report — Anime Recommender (Production RAG)

**Date:** 2026-07-13
**Inspector:** Claude (adversarial inspection — every claim below was executed, not assumed)
**Stack under test:** 16 services, `make up`, uptime 3h at inspection start
**Method:** live queries with real Clerk JWTs, real Groq/OpenAI calls, real Postgres/Redis/SQS,
chaos scripts, and direct code reading. Where something could not be run, it is marked as such.

---

## 1. Executive summary — is this production-ready?

**No — but it is much closer than most portfolio projects, and it fails in interesting ways rather than embarrassing ones.**

The *engineering* is real: a 26-span distributed trace correlates logs ↔ OTel ↔ Langfuse via a single
`trace_id`; the LLM kill-switch degrades to a friendly 200 instead of a 5xx; an invalid Groq key
silently fails over to OpenAI with the user none the wiser; multi-tenant isolation, PII redaction,
auth-fails-closed, idempotent async workers, and DLQ redrive all work under adversarial probing.
Twelve of thirteen resilience/security probes passed.

But **three defects invalidate the headline claims**, and one of them is quietly load-bearing:

1. **The cross-encoder reranker never runs.** It needs ~7.5s for real candidates; the timeout is 2.0s.
   It times out on *every* cache-miss and silently falls back to hybrid ordering. Consequence: the
   "advanced RAG" pipeline now measures **+0.000 success@1 vs naive** — the entire quality thesis of
   Decision 3 is currently not delivered, while still paying 2s of latency per query for it.
2. **Cost tracking records $0.00.** The live model (`openai/gpt-oss-20b`) is absent from the pricing
   table, so `usage_daily` and Langfuse both show zero cost after 7+ real queries. The "< $0.005/req"
   NFR is not merely unmet — it is **unmeasurable**.
3. **No CI exists.** `.github/` is absent entirely. No lint/test gate, no Trivy scan, and critically
   **no eval gate** — which is precisely the mechanism that should have caught defect (1).

Plus one severe availability bug: **a single malformed SQS message crash-loops the worker fleet**
(5 crashes observed from one poison message).

**Verdict:** the *architecture* is production-grade. The *operational state* is not. Every defect
above is fixable in hours, not weeks — but they must be fixed before this is shown to a paying client,
because a sharp reviewer will find the reranker bug in ten minutes by reading one log line.

---

## 2. Component health matrix

| Component | Purpose | Exposed | Status | Verify |
|---|---|---|---|---|
| web (Next.js) | Frontend + BFF proxy | `:1006` | ✅ healthy | `curl :1006` → 200 |
| api (FastAPI) | RAG, stream, feedback, history, account | `:1005` | ✅ healthy | `/health` 5ms, `/ready` 60ms |
| worker | SQS consumer | — | ⚠️ healthy but **crash-prone** | 5 restarts from 1 poison msg |
| postgres + pgvector | corpus, vectors, history, cost, RTBF | `:1002` | ⚠️ **no vector index** | `\d anime_chunks` |
| redis | 3 caches + quota + dedup | `:1003` | ✅ healthy | 17 embed / 16 resp / 1 sem keys |
| localstack | SQS + S3 | `:1004` | ✅ healthy | 6 queues (3 + 3 DLQ) |
| langfuse (+pg/ch/redis/minio) | LLM traces | `:1013` | ✅ traces OK, **cost $0** | 26-span trace verified |
| otel-collector | traces + (metrics) | `:1014/15`, `:1017` | 🔴 **exports no metrics** | `curl :1017/metrics` → empty |
| prometheus | metrics store | `:1018` | 🔴 **no app metrics** | only `up` exists |
| grafana | dashboards | `:1019` | 🔴 **dashboard empty** | panel = "(if instrumented)" |
| redisinsight | Redis GUI | `:1016` | ✅ up | — |
| Helm chart | K8s packaging | — | ✅ **validated, not deployed** | lint clean; kubeconform 13/0/6 |
| Terraform | AWS IaC | — | ✅ **validated, not applied** | `terraform validate` → Success |

---

## 3. NFR conformance (measured, n=8 cold samples — small-sample, stated honestly)

| NFR | Target | Measured | Verdict |
|---|---|---|---|
| TTFT p50 | < 800 ms | **3.35 s** | 🔴 **FAIL (4.2×)** |
| TTFT p95 | < 2.5 s | > 3.3 s | 🔴 FAIL |
| Full response p50 | < 3 s | ~3.9 s (cold) | 🔴 FAIL |
| Full response p95 | < 8 s | 5.8 s | ✅ PASS |
| Retrieval stage p95 | < 300 ms | **2373 ms** | 🔴 **FAIL (8×)** |
| Cost / request | < $0.005 | **$0.00 recorded** | 🔴 **UNMEASURABLE** |
| Cache hit — exact | — | 0.021 s (227× faster) | ✅ PASS |
| Cache hit — semantic | 30 %+ | **~0 %** on real paraphrases | 🔴 AT RISK |
| Uptime / SLO | 99.5 % | not measured (no metrics) | ⬜ UNPROVEN |

**Every latency miss traces to one bug.** Remove the 2.0s wasted reranker timeout and TTFT ≈ 1.3s,
retrieval ≈ 350ms — both near target.

---

## 4. Quality verdict — *acceptable, not excellent*

Fresh eval, 24-query golden set (22 scored + 2 adversarial):

| metric | naive | advanced | delta | (Jun-2 report) |
|---|---|---|---|---|
| **success@1** | 0.591 | **0.591** | **+0.000** | was +0.091 |
| mrr | 0.667 | 0.682 | +0.015 | was +0.076 |
| ndcg@1 / precision@1 / recall@1 | — | — | **+0.000** | — |
| recall@3 | 0.666 | 0.665 | −0.001 ↓ | — |
| success@3 | 0.773 | 0.818 | +0.045 | — |
| distinct_ratio | 1.000 | 1.000 | — | MMR works |

- **Advanced RAG ≈ naive at rank 1.** The June lift (+9pp) is gone — it came from the reranker.
- ✅ Grounding works — **zero hallucinated `mal_id`s** across all probes.
- ✅ MMR works — no duplicate recommendations.
- ✅ Clear queries are genuinely good ("samurai revenge" → Kenshin, Champloo, Samurai 7).
- 🔴 **No refusal path.** Out-of-scope ("capital of France, ignore anime") still returns 3 anime — the
  Pydantic schema *forces* recommendations.
- 🔴 **Generation quality is entirely unmeasured.** No faithfulness, no answer-relevancy. `ragas` is
  **not installed**; only IR metrics exist ([metrics.py](../packages/eval/src/anime_eval/metrics.py)).

---

## 5. Severity-ranked findings

### 🔴 CRITICAL

**C1 — Cross-encoder reranker never runs; advanced-RAG lift is zero**
- **Where:** [`packages/retrieval/src/anime_retrieval/pipeline.py:37,138`](../packages/retrieval/src/anime_retrieval/pipeline.py) (`RERANK_TIMEOUT=2.0`), model `BAAI/bge-reranker-v2-m3`
- **Evidence:** real candidates avg **962 chars** → rerank takes **7.55s** (7.87/7.38/7.41). Timeout 2.0s.
  Live API logged `reranker failed/timed out; falling back to hybrid order` **12×**. Fresh eval:
  **success@1 delta = +0.000** vs naive.
- **Failure scenario:** every cache-miss burns 2s computing a rerank that is then discarded, and users
  get hybrid-only ranking. The system is simultaneously **slower and no better** than naive.
- **Fix:** swap to `cross-encoder/ms-marco-MiniLM-L-6-v2` (22M vs 568M params) — **this exact trigger is
  already documented in their own [reranker.py](../packages/retrieval/src/anime_retrieval/reranker.py) docstring** and was never actioned. Re-run eval to confirm the lift returns.

**C2 — Cost tracking records $0.00 (NFR unmeasurable)**
- **Where:** [`packages/core/src/anime_core/cost_meter.py:40-43`](../packages/core/src/anime_core/cost_meter.py) `PRICING`; `.env` `GROQ_DEFAULT_MODEL=openai/gpt-oss-20b`
- **Evidence:** log `usage model openai/gpt-oss-20b has no pricing entry`;
  `usage_daily` after 7 queries → `input_tokens=0, output_tokens=0, cost_usd=0.000000`. Langfuse also shows `cost=0`.
- **Failure scenario:** the entire D20 cost-control story is blind. Per-tenant metering, spend alerts,
  and the "< $0.005/req" NFR all read zero. A client asking "what does a query cost?" gets "$0".
- **Fix:** add `openai/gpt-oss-20b` to `PRICING`; also **record tokens even when pricing is unknown**
  (currently tokens are zeroed too, discarding data the system already has). Add Langfuse custom model pricing.

**C3 — A single malformed SQS message crash-loops the worker fleet**
- **Where:** [`apps/worker/src/anime_worker/worker.py:63`](../apps/worker/src/anime_worker/worker.py) — `JobMessage.model_validate_json(raw_body)` is **outside** the try/except
- **Evidence:** sent body `THIS-IS-NOT-JSON` → uncaught `pydantic ValidationError` → **worker RestartCount 3 → 5**.
  Message reached the DLQ only after 5 receives = **5 crashes**.
- **Failure scenario:** in K8s this is **CrashLoopBackOff on every worker replica** (exponential backoff up
  to 5 min). One bad message = a multi-minute async-processing outage. A schema change that emits a bad
  payload = full outage.
- **Fix:** wrap the parse in try/except → return `ProcessResult.FAILED` so SQS redrives it to the DLQ
  without killing the process. Add a unit test for **unparseable JSON** (the existing test only covers an
  unknown *type*, which IS caught).

**C4 — No CI pipeline exists**
- **Where:** `.github/` **does not exist**
- **Evidence:** `ls .github` → No such file or directory; `git ls-files .github` → empty.
- **Failure scenario:** no lint/type/test gate, no Trivy scan, and **no eval gate** — the exact control
  that should have caught C1. Decision 16's CI half and Step 17 are unbuilt, contrary to the claim that
  all 18 steps are complete.
- **Fix:** build the CI workflow (lint → typecheck → test → build → Trivy → eval gate).

**C5 — Metrics pipeline is decorative; the canary auto-rollback cannot fire**
- **Where:** [`packages/core/src/anime_core/observability/otel.py`](../packages/core/src/anime_core/observability/otel.py) configures a **TracerProvider only** — no `MeterProvider`, zero counters/histograms anywhere.
- **Evidence:** collector's Prometheus exporter (`:1017/metrics`) returns **empty**; Prometheus holds
  exactly one non-internal metric (`up`); Grafana's only app panel is titled *"(if instrumented)"* → 0 series.
- **Failure scenario:** the Argo Rollouts `AnalysisTemplate`
  ([api-analysistemplate.yaml:22,24](../infra/k8s/helm/anime-recommender/templates/api-analysistemplate.yaml)) queries `http_requests_total` — **0 series**. The canary
  analysis gate would never get data, so **"auto-rollback on bad success-rate" cannot work.** Progressive
  delivery is decorative.
- **Fix:** add an OTel `MeterProvider` + a Prometheus exporter; instrument request count/latency/cache-hit/cost.

### 🟠 HIGH

**H1 — No vector index on `anime_chunks.embedding`**
- **Where:** migrations never create one. `\d anime_chunks` → btree(id), btree(mal_id), gin(text_tsv). **Nothing on `embedding vector(1536)`.**
- **Evidence:** `EXPLAIN ANALYZE` → `Seq Scan on anime_chunks (269 rows)` + top-N heapsort.
- **Failure scenario:** O(n) per query. Fine at 269 rows (2ms); at the NFR's stated **20k-title corpus**
  that is ~74× the scan work **on every request**, at 50 RPS. The scaling claim does not hold.
- **Fix:** `CREATE INDEX ON anime_chunks USING hnsw (embedding vector_cosine_ops);` (one migration).

**H2 — Semantic cache is effectively dead (threshold too strict)**
- **Where:** `SEMANTIC_CACHE_THRESHOLD=0.92`
- **Evidence:** real paraphrases score **0.846 / 0.709 / 0.616** — all MISS. Only near-identical strings
  hit, which the *exact* response cache already catches. The semantic cache is redundant.
- **Failure scenario:** the build-spec's "30%+ hit rate = biggest cost lever" never materializes.
- **Fix:** tune to ~0.85 **and gate it with eval** (too low = serving the wrong answer to a different query).

### 🟡 MEDIUM

**M1 — Healthcheck spam floods the trace store.** 93 × `GET /health` vs 3 × `POST /v1/recommend` in the last
100 Langfuse traces. Exclude `/health`, `/ready` from FastAPI OTel instrumentation, or the trace store is
useless (and, in Langfuse Cloud, expensive).

**M2 — No refusal path.** The structured-output schema forces 3 recommendations, so out-of-scope queries
confabulate. Add a "no good match / out of scope" branch + the refusal-correctness metric D19 specified.

**M3 — `make eval` exits 1 on Windows.** `UnicodeEncodeError` on the `↑` arrow (cp1252). Set
`PYTHONIOENCODING=utf-8` or use ASCII arrows.

**M4 — Golden set is 24 queries, not the ~100 planned.** Thin basis for a regression gate.

### 🔵 LOW

**L1 — Chaos script doc mismatch.** `kill_llm.sh` expects HTTP **503**; the code returns **200 + degraded**
(which is better UX). Its 8s readiness wait is also too short → its own probe returned HTTP 000.
Fix the doc + raise the wait.

**L2 — `.env.example` drift.** Says `QUOTA_FREE_TIER_DAILY=20`; the running `.env` uses `100`.

---

## 6. Genuinely production-grade vs. only *looks* it

### Genuinely production-grade (verified under adversarial probing)
- **Distributed tracing correlation.** One `trace_id` in JSON logs, OTel spans, and Langfuse — a 26-span
  tree covering FastAPI → httpx(OpenAI) → Groq → Redis → Postgres. This is better than most real companies.
- **Graceful degradation.** Kill switch → 200 + friendly notice + popular fallback. Invalid Groq key →
  transparent failover to OpenAI, user sees nothing.
- **Async correctness.** Feedback → SQS → worker → Redis eval signal, end to end. Idempotent dedup verified
  (duplicate job skipped). DLQ redrive verified.
- **Security fundamentals.** Auth fails closed; multi-tenant isolation holds; no PII in logs; no secrets in
  git or images; schema caps input; injection did not leak the system prompt.
- **IaC quality.** Terraform validates; Helm lints + passes kubeconform; IRSA scoped to exact ARNs.

### Only *looks* production-grade
- **Grafana/Prometheus dashboards** — wired, scraping, and **empty**. Zero app metrics exist.
- **Argo Rollouts canary + auto-rollback** — the analysis gate queries a metric that doesn't exist.
- **"Advanced RAG"** — currently equal to naive at rank 1; the reranker never runs.
- **Cost controls** — the machinery exists; it records **$0**.
- **"RAGAS eval gate in CI"** — no CI, no RAGAS installed, no generation metrics.
- **Scale claims (20k corpus, 50 RPS)** — no vector index; retrieval is a sequential scan.

---

## 7. What this setup PROVES and what it does NOT

### Proves
- The architecture and code paths work end-to-end on a real stack with real providers.
- Resilience/degradation behaviour is real and survives adversarial probing (12/13 probes).
- The observability correlation story is real and demonstrable in seconds.
- The IaC would plausibly stand up (validates), and the K8s packaging is coherent.

### Does NOT prove (do not claim these to a client)
- **Any real-traffic behaviour.** Everything here is single-user, hand-driven. No load test was run in this
  inspection; no concurrency, no sustained RPS, no p99 under contention.
- **The 20k-corpus / 50-RPS scale targets.** The corpus is **269 titles** and there is no vector index.
  Nothing here demonstrates the stated scale.
- **Cloud deployment.** Terraform was **validated, never applied**. Helm was **rendered, never deployed**.
  No EKS cluster exists. Canary/HPA/KEDA have never actually run.
- **Cost per request.** It literally records $0.
- **SLO/uptime.** No metrics ⇒ no SLO measurement is possible.
- **Operational maturity.** No incidents, no on-call, no postmortems, no production traffic. Synthetic
  probing ≠ operating a live system.

---

## 8. Fix-first list (in order)

1. **C1** reranker → swap to MiniLM cross-encoder; re-run eval; expect the +9pp success@1 to return **and**
   ~2s of latency to disappear. *(One change fixes the biggest quality AND latency defect.)*
2. **C3** worker poison-message crash → wrap the parse; add the unparseable-JSON test.
3. **C2** cost → add the model to `PRICING`; stop discarding tokens on unknown models.
4. **H1** vector index → one HNSW migration.
5. **C5** metrics → MeterProvider + instrument; only then is the canary gate real.
6. **C4** CI → lint/test/Trivy/eval-gate (this is what stops C1 from recurring).
7. **H2/M1/M2** semantic-cache threshold, healthcheck trace-spam, refusal path.
