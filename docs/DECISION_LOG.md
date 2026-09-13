# Architecture Decision Log
## Anime Recommender — a production-grade RAG application

| | |
|---|---|
| **Project** | Anime Recommender SaaS |
| **Service package** | Production-grade RAG application |
| **Status** | Locked. Ready for implementation. |

---

## Non-functional requirements

| Dimension | Target |
|---|---|
| TTFT (time-to-first-token) p50 / p95 / p99 | < 800 ms / < 2.5 s / < 5 s |
| Full response (3 recs, ~400 tok) p50 / p95 | < 3 s / < 8 s |
| Retrieval-only stage p95 | < 300 ms |
| Sustained RPS, designed-for | ~50 RPS |
| Peak RPS, designed-for | ~200 RPS |
| Demonstrated RPS via load test | 100 RPS sustained |
| Architecture headroom before redesign | ~500 RPS |
| MAU / DAU target (12–18 mo) | 100k / 20k |
| Peak concurrent users | ~1,000 |
| Corpus size (v1.x target) | ~20k anime titles |
| Uptime SLO v1 / stretch | 99.5% / 99.9% |
| RTO / RPO | < 30 min / < 5 min |
| Cost per request, hard cap | < $0.005 USD |
| Cost per request, target avg | < $0.001 USD |
| Monthly budget @ 10k MAU | < $300 |
| Monthly budget @ 100k MAU | < $3,000 |
| Hard kill switch | 200% of monthly budget |
| Compliance | GDPR-aware from day 1; SOC 2 / HIPAA out of scope v1 |
| Region | Single (us-east-1) |
| Multi-region trigger | EU MAU > 10% of total |

---

## Out-of-scope (anti-creep)

Explicitly NOT in v1 (each can be reconsidered later):

1. Fine-tuning the LLM (RAG is sufficient)
2. Agentic features (tools, multi-step planning)
3. Multi-modal (no images, no audio)
4. MAL / AniList account integration
5. Mobile native apps (web responsive only)
6. Real-time collaboration / sharing
7. Stripe / payments (quota plumbed, billing deferred)
8. Localization beyond English
9. Voice / conversational telephony
10. Per-user fine-tuning / personalized model adaptation
11. Self-hosted LLM (vLLM is v2 trigger)
12. Multi-region deployment
13. SOC 2 audit
14. Admin / moderation UI for corpus
15. Community / social features

---

## At-a-glance summary

Legend: **★** = chosen option · **Prod-grade** ✓ = production-appropriate · **Rev** = reversibility (E/M/H).

| # | Decision | Options | Pick | Why | Prod | Rev | Trigger to revisit |
|---|---|---|---|---|---|---|
| 1 | Primary database | Postgres / MySQL / DynamoDB / MongoDB | **★** Postgres (Amazon RDS) | Relational fit (users→queries→feedback); GDPR-friendly; hosts pgvector | ✓ | H | DB CPU >70% sustained after vertical scale + 2 read replicas |
| 2 | Vector database | pgvector / Qdrant / Pinecone / Weaviate / Milvus / Chroma | **★** pgvector | 20k docs is small; one DB to operate; hybrid via PG FTS | ✓* | M | Corpus >500k OR retrieval p95 >200 ms after tuning |
| 3 | RAG paradigm | Naïve / Advanced / Agentic / Multi-query / HyDE | **★** Advanced (hybrid + cross-encoder rerank + MMR) | Single biggest quality lever; a common production default | ✓ | E | Eval shows recall is bottleneck → add multi-query / HyDE |
| 4 | LLM tiering | Single Groq / Two-tier+fallback / Frontier baseline / Self-host | **★** Two-tier Groq (8B→70B) + OpenAI gpt-4o-mini fallback | Fast TTFT + cost ceiling + outage resilience | ✓ | E | Groq sustained cost >$2k/mo OR SLA misses → vLLM |
| 5 | Embedding model | MiniLM-L6 / bge-large / OpenAI 3-small / OpenAI 3-large / Cohere v3 | **★** OpenAI `text-embedding-3-small` (1536-dim) | Latency gate: 3-large p50 399 ms; 3-small ~100–150 ms faster server-side; 5× cheaper; | ✓ | H | RAGAS context P/R degrades vs 3-large baseline → revert to 3-large |
| 6 | Orchestration framework | Thin custom + LCEL / Full LangChain v1 / LlamaIndex / Haystack / None | **★** Full LangChain v1 — modern chain factories (`create_retrieval_chain`, NOT deprecated `RetrievalQA`) | Uses the LangChain ecosystem; modern v1 avoids deprecation tax | ✓ | M | LangChain breaking changes become disruptive → swap to custom |
| 7 | Backend lang/framework | Python+FastAPI / Node+NestJS / Go / Python+Litestar | **★** Python + FastAPI, REST + SSE, Pydantic v2 | Strongest language; async-native; Pydantic at every boundary | ✓ | H | None foreseen |
| 8 | Frontend framework | Next.js / Remix / SvelteKit / Streamlit (excluded) | **★** Next.js App Router + Tailwind + shadcn/ui | Production UX; Server Components + SSE streaming; React skill fit | ✓ | H | None foreseen |
| 9 | AuthN / AuthZ | Clerk / Auth.js / AWS Cognito / Supabase Auth | **★** Clerk (email + Google + Discord OAuth) | Fastest to ship credible multi-tenant consumer auth | ✓ | M | Clerk >$200/mo (~70k MAU) → migrate to Auth.js |
| 10 | Caching strategy | Redis (ElastiCache) / in-process LRU / Memcached / Upstash | **★** Redis: normalized-response + embedding caches | Cost+latency lever. ⚠️ **Revised 2026-07-14**: semantic cache REMOVED — measured unsafe at any threshold (antonym pairs out-score paraphrases on cosine) | ✓ | E | Revised — see D10 |
| 11 | Queue / async work | ARQ+SQS / Celery+Redis / SQS+EKS workers / Lambda / Temporal | **★** SQS + dedicated EKS worker Deployments (KEDA autoscale on queue depth) | One queue system; KEDA-native; cleaner separation | ✓ | E | None foreseen |
| 4b | Multi-venue serving | Hosted only / +vLLM self-host / +SGLang self-host / both engines | **★** +vLLM self-hosted venue, dark behind `LLM_VENUE_ROUTING_ENABLED=false` | Measured: 38 ms TTFT, 67.9 tok/s — inside NFR by 20–45×. vLLM over SGLang on operational cost, not speed (2.6% gap) | ✓ | E | Workload gains long shared prefixes → re-measure, SGLang may win |
| 12 | Inference serving | Groq API / Bedrock / vLLM self-host / SageMaker | **★** Groq hosted API (with OpenAI as fallback per D4); **+ self-hosted venue per D4b** | Fastest TTFT in market; right unit economics at our scale | ✓* | M | Sustained Groq cost >$2k/mo OR SLA miss → vLLM |
| 13 | Observability | OTel→Grafana + Langfuse / LangSmith / Datadog / Full self / CloudWatch only | **★** OTel SDK → Grafana Cloud (free tier) + Langfuse (self-host on EKS) | Portable instrumentation; covers app + LLM-specific layers | ✓ | H (high — OTel makes backend portable) | Grafana free tier exceeded |
| 14 | Cloud provider | AWS / GCP / Azure / Multi-cloud | **★** AWS, us-east-1, single region v1 | Broadest managed-service coverage; single-cloud simplicity | ✓ | H | EU MAU >10% of total → consider eu-west-1 secondary |
| 15 | Container / orch / IaC | EKS+Helm+Terraform (pre-locked) / ECS Fargate / Cloud Run | **★** EKS (managed K8s) + Helm + Terraform (modular) | Managed Kubernetes + modular IaC | ✓ | H | None foreseen |
| 16 | CI/CD pipeline | GH Actions+ArgoCD / GitLab CI / Jenkins / CircleCI | **★** GitHub Actions + ArgoCD (GitOps) + Argo Rollouts (canary) + Trivy + **RAGAS eval gate** | Skill fit; progressive delivery + eval-in-CI | ✓ | M | None foreseen |
| 17 | Secrets / config | Secrets Manager+ESO / .env / K8s Secrets only / Vault | **★** AWS Secrets Manager + External Secrets Operator + per-env Helm values | Industry standard for K8s+SM; auto-sync; rotation-ready | ✓ | E | None foreseen |
| 18 | Security posture | (composite — layered mitigations) | Prompt-injection defense + output filtering + log redaction + ACL-at-retrieval + rate limits + cost kill switch + standard web hygiene | Each threat real; mitigations cheap individually; layering is the point | ✓ | E (each independent) | SOC 2 audit pursued → escalate posture |
| 19 | Evaluation strategy | RAGAS + DeepEval + golden + online + A/B / LangSmith only / No eval | **★** RAGAS + custom metrics + ~100 golden set + 5% online sampling + A/B + CI gate | Eval is the production credibility moat | ✓ | E | None foreseen — additive |
| 20 | Cost controls | (composite — layered) | Per-req budget + model routing + per-user quotas + per-tenant meter + spend alerts (50/75/90%) + 200% kill switch | Single-layer mitigation insufficient; single-layer mitigation is insufficient | ✓ | E | None foreseen |
| 21 | Failure modes & degradation | (composite — per failure mode) | Per-component fallback chains + circuit breakers (pybreaker) + retries w/ jitter + idempotency keys + timeouts | Explicit "what does user see when X fails" — without this, prod-grade is empty | ✓ | E | None foreseen — additive |
| 22 | Repo structure | Monorepo / Polyrepo | **★** Monorepo  (`apps/`, `packages/`, `infra/`, `tests/`, `docs/`) | Atomic PRs across stack; single CI; small-team fit | ✓ | H | None foreseen |

**Summary:** 22 architecture decisions, each production-appropriate for the
target scale. The load-bearing ones — observability (D13), EKS + IaC (D15),
CI/CD eval-gate (D16), security (D18), evaluation (D19), cost controls (D20),
and resilience (D21) — are documented in full below with options, reasoning,
trade-offs, and revisit triggers.

---

## Detailed decisions

> Each decision is the **final, locked form** after review and the D5/D6/D11 revisions. See [Revision history](#revision-history) for what changed mid-phase.

---

### Decision 1 — Primary database

**Question:** What is the primary OLTP store for users, query history, feedback, per-tenant metadata, ACL?

**Options:**
- A — PostgreSQL (RDS): relational, has `pgvector`, ACID, AWS-managed.
- B — MySQL (Aurora): similar profile, no `pgvector` equivalent.
- C — DynamoDB: NoSQL, infinite horizontal scale, poor ad-hoc query, painful GDPR deletion.
- D — MongoDB Atlas: extra vendor, no clear advantage.

**Decision:** **PostgreSQL via Amazon RDS** (single instance v1; read replica at v1.x when load demands).

**Reasoning:** Our data is relational; GDPR deletion is straightforward with cascading FKs; cost/quota counters need ACID; `pgvector` extension keeps the "one DB" option open (Decision 2). RDS-managed = one less thing to operate.

**Trade-offs accepted:** Vertical-scale-first; we'll partition + add replicas at >500 RPS.

**Reversibility:** **Hard.** Migrations and ORM coupling accumulate. Trigger to revisit: sustained DB CPU >70% after vertical scale + 2 read replicas.


---

### Decision 2 — Vector database

**Question:** Where do anime embeddings live, and how do we filter/search them?

**Options:**
- A — pgvector (Postgres extension): one DB, ACID over docs+vectors, hybrid via PG FTS, per-tenant filtering via WHERE.
- B — Qdrant (self-host or cloud): a common production default, scales further.
- C — Pinecone (managed): vendor lock, per-vector pricing.
- D — Weaviate / Milvus / Chroma: similar to Qdrant; Chroma is dev-only.

**Decision:** **pgvector** in v1, with `VectorIndex` abstraction so swap-to-Qdrant is a 1-day job.

**Reasoning:** Corpus is ~20k titles. Qdrant at this size is over-engineering at this volume — pgvector is appropriate when the corpus is small. One DB to operate is a real win at our team size.

**Trade-offs accepted:** Lower performance ceiling (we'll measure).

**Reversibility:** **Moderate** — `VectorIndex` interface is the affordance. Trigger: corpus >500k vectors OR retrieval p95 >200 ms after tuning OR per-tenant index noisy-neighbor.


**Primer — pgvector:** Postgres extension that adds `vector(N)` column type and HNSW / IVF / cosine indexes. `CREATE EXTENSION vector; SELECT * FROM anime_chunks ORDER BY embedding <=> '[...]' LIMIT 10;`. Same operational story as Postgres — no new database to manage.

---

### Decision 3 — RAG paradigm and flavor

**Question:** Which RAG paradigm, and which advanced techniques in v1?

**Options:**
- A — Naïve RAG (single dense, stuff context): what `demo/` does; poor recall on preference queries.
- B — Advanced RAG (hybrid + reranker + MMR + structured output): a common production default.
- C — Agentic RAG: overkill, latency- and cost-hostile.
- D — Multi-query / HyDE: 2–4× LLM cost; defer until eval proves recall is the bottleneck.

**Decision:** **Advanced RAG v1** — hybrid (BM25 + dense via pgvector) → cross-encoder reranker (`bge-reranker-v2-m3`, CPU in-process) → MMR diversifier (top-3) → LLM generates 3 structured recommendations.

**Reasoning:** Highest-leverage choice in the transformation. Hybrid recovers lexical matches dense embeddings miss; reranker substantially improves precision; MMR prevents three near-identical recs. Multi-query / HyDE deferred — measure first.

**Trade-offs accepted:** ~50–150 ms added latency from reranker (within budget). More moving pieces.

**Reversibility:** **Easy** — each stage is pluggable.


**Eval result (2026-05-27, golden v1, 22 scored queries — advanced vs naïve dense-only):** Qualified win. Rank-1 quality clearly improved (precision@1 / success@1 / ndcg@1 all +0.091 → 0.682, ~+15% relative; mrr +0.076 → 0.742) — the **cross-encoder reranker is earning its keep**. But recall@3 *regressed* −0.050 (0.666 → 0.615): MMR at λ=0.7 over-diversified, evicting relevant franchise entries (Evangelion/Gundam sequels) from slots 2-3 where similarity is actually correct. **Action:** raised MMR λ 0.7 → 0.85 (config-driven via `MMR_LAMBDA`) to favor relevance. **Re-eval result:** ndcg@3 +0.018 (0.643→0.660), precision@3 +0.015 (0.303→0.318), recall@3 partial recovery +0.019 (0.615→0.634, still −0.031 vs naïve); rank-1 gains held exactly (+0.091). success@3/mrr wobbled (0.818→0.773 / 0.742→0.727) — one-query-level movement = **noise on a 22-query set**. **Conclusion: λ=0.85 locked; further λ tuning deferred until the golden set grows to ~100 (Step 18) — sweeping λ on 22 queries fits noise.** The stable, real result across both runs is the reranker's rank-1 win; recall@3 −0.031 vs naïve is an accepted minor trade. Hybrid (BM25) contribution not isolated in this A/B.

**Primer — `bge-reranker-v2-m3`:** ~568M cross-encoder that takes (query, candidate) pairs and outputs a relevance score, much more accurate than embedding cosine alone. CPU-fast; second retrieval stage after pulling top-20 from vector index, narrowing to top-5.

---

### Decision 4 — LLM provider + tiering strategy

**Question:** Which LLM(s), how do we tier for cost, and what is the outage-fallback chain?

**Options:**
- A — Single Groq Llama-3.1-8b-instant: cheap and fast, but no fallback.
- B — Two-tier Groq + OpenAI fallback: cost-controlled escalation + resilience.
- C — Claude Haiku / GPT-4o-mini baseline: 5–10× the cost; blows cost cap at scale.
- D — Self-host vLLM: bad economics at our QPS.

**Decision:** **B — two-tier Groq + OpenAI fallback.** Default `llama-3.1-8b-instant`; escalation `llama-3.3-70b-versatile`; outage fallback `gpt-4o-mini`. All behind a single `LLMClient` interface.

**Reasoning:** Hits $0.005/req cap with margin (8B ~$0.0003/req at typical sizes). Escalation triggered by: query length >N or low first-pass groundedness. OpenAI fallback answers Decision 21's "Groq down" failure mode.

**Trade-offs accepted:** Routing layer adds complexity; mixed-provider cost forecasting messier.

**Reversibility:** **Easy** — model strings in config, providers behind adapter.


---

### Decision 4b — Multi-venue serving **[ADDED 2026-09-12]**

**Question:** Should a self-hosted open-weight venue join the tiering strategy alongside the hosted APIs, and if so, which engine?

**Context:** D4 and D12 both deferred self-hosting with the trigger "sustained Groq cost >$2k/mo OR SLA misses". That deferral was made on *estimated* economics with no measured latency data for a self-hosted venue. S19/S20 removed the estimate.

**Options:**
- A — Hosted APIs only (status quo per D4/D12): simplest; no GPU ops; every token billed.
- B — Add a self-hosted vLLM venue as a third tier: $0/token for the simple end of the workload; adds a GPU dependency and a SPOF.
- C — Add a self-hosted SGLang venue instead: ~2.8% faster decode; 52.2 GB image; less mature ecosystem.
- D — Run both engines in production: maximum flexibility; doubles operational surface for a 3% difference.

**Decision:** **B — add a self-hosted vLLM venue as an optional tier**, shipped dark behind `LLM_VENUE_ROUTING_ENABLED=false`. SGLang is retained as a benchmarked alternative with a documented flip condition, not as a parallel production tier.

**Measured evidence** (`docs/GPU_VENUE.md`, Qwen2.5-7B-AWQ on RTX 3060, 20 runs, quiet host):

| | vLLM | SGLang | NFR |
|---|---|---|---|
| TTFT p50 | 38.2 ms | 39.9 ms | < 800 ms |
| TTFT p99 | **93.5 ms** | 249.5 ms | — |
| tok/s | 67.9 | **69.8** | — |
| total, 146 tok | 2203 ms | **2145 ms** | < 8000 ms p95 |

**Reasoning:** The deferral in D4/D12 assumed self-hosting could not meet latency needs at small scale. It can — by 20–45×. The engine choice, however, is *not* decided by speed: a 2.6% total-time gap is inside the noise of an N=20 sample. vLLM wins on operational cost — 23 GB smaller image, faster cold start, 2.67× better TTFT tail, larger ecosystem.

**Trade-offs accepted:** A home GPU is a single point of failure with no HA and a residential uplink — so the venue is *additive*, never load-bearing: the fallback chain (self-hosted → Groq 8B → Groq 70B → OpenAI) must remain proven. Cost attribution gets harder: self-hosted is $0/token but GPU-hours are real and must be amortised separately in the cost meter. Production use requires a GPU node group, which is a separate cost decision (P9.6).

**Reversibility:** **Easy** — the venue is behind a feature flag that defaults off, registered as one more entry in the venue registry. Disabling it restores exactly today's behaviour.

**Flip condition (engine):** SGLang's RadixAttention advantage is invisible on this workload (10 distinct short prompts, no shared prefixes beyond the system message). **If the workload gains long shared contexts — multi-turn chat, agent loops, batch over a shared document — re-measure; the recommendation may invert.**

**Supersedes:** the "self-host only above ~150 QPS" reasoning in D12, which was about *cost* economics and remains true for that question. D4b is about *capability*: self-hosting is now a proven option at any scale, gated on operational readiness rather than QPS.


---

### Decision 5 — Embedding model **[REVISED 2026-05-26, 2026-05-27]**

**Question:** Which embedding model, what dimensionality, multilingual?

**Options:**
- A — `sentence-transformers/all-MiniLM-L6-v2` (384-dim, free, local): cheap and fast; English-only; quality below frontier.
- B — `BAAI/bge-large-en-v1.5` (1024-dim, open, top MTEB): free; GPU-friendly.
- C — OpenAI `text-embedding-3-small` (1536-dim, hosted): strong MTEB; per-token cost; vendor coupling. **Current pick.**
- C′ — OpenAI `text-embedding-3-large` (3072-dim, hosted): top-tier MTEB; ~100–150 ms slower per query; 5× more expensive.
- D — Cohere embed-v3: similar to OpenAI; native multilingual.

**Decision:** **C — OpenAI `text-embedding-3-small` (1536-dim).**

**Reasoning (2026-05-27 revision):** Per-query embedding p50 with `text-embedding-3-large` was measured at 399 ms (latency gate run). The structural floor is ~200 ms network RTT from the deployment region to OpenAI US-East — 3-large cannot meet the 300 ms gate at this network distance. `text-embedding-3-small` has genuinely lower server-side processing time (~100–150 ms less than 3-large), bringing p50 into the WARN or PASS range. Quality is still MTEB-competitive for anime synopsis matching. Semantic cache (D10) amortizes the per-query cost regardless of model tier.

**Concrete cost:** One-time corpus embedding ~3 M tokens × $0.02/1M = **~$0.06** one-time. Per uncached query ~20 tokens = **~$0.0000004** ≈ $1.50/mo at 50 RPS with 30% cache hit. Storage delta: 1536-dim × 4 bytes × 20k = ~120 MB in pgvector — trivial.

**Trade-offs accepted:** (1) **~5–10% lower MTEB score vs 3-large** — tolerable for anime preference queries; measure during eval; (2) **OpenAI dependency from day 1** (was deferred to fallback only); (3) **GDPR data flow** — query content traverses OpenAI servers (US), disclosed in privacy policy with "data not used for training" setting enabled; (4) **Re-embed costs real money** — versioning + idempotency in ingestion are non-negotiable.

**Reversibility:** **Hard** (re-embed corpus required for swap; ~$1 in API costs with 3-large).

**Trigger to revisit:** RAGAS context-precision/recall during RAGAS eval shows significant degradation vs 3-large baseline → revert to 3-large, accept geographic latency, or move to local model.

**Resolution (2026-05-27):** **3-small ACCEPTED on cost/latency grounds; quality A/B vs 3-large NOT run.** The Step 4 golden-eval established 3-small's absolute baseline (advanced retriever: success@3=0.818, mrr=0.742 — solid in absolute terms). User chose to accept rather than spend the re-ingest + eval cycle to A/B against 3-large. **This is an honest open item: 3-small is unproven *relative to* 3-large on quality.** Trigger to revisit unchanged — if production retrieval quality disappoints, run the 3-large A/B before other tuning.


---

### Decision 6 — Orchestration framework **[REVISED 2026-05-26]**

**Question:** What orchestrates retrieve → rerank → generate?

**Options:**
- A — Thin custom Python + LCEL: smallest surface, no framework lock.
- B — Full LangChain v1 (modern chain factories — `create_retrieval_chain`, `create_stuff_documents_chain`, `create_history_aware_retriever`).
- B′ — LangChain *classic* (`langchain_classic.RetrievalQA`): deprecated; carries migration debt.
- C — LlamaIndex: best for ingestion, doesn't add to query side here.
- D — Haystack: similar overhead.
- E — No framework at all: cleanest, slightly more code.

**Decision:** **B — full LangChain v1 with modern chain factories.** Explicitly **NOT** `langchain_classic.RetrievalQA` (deprecated).

**Reasoning:** Modern v1 chain factories give the same level of abstraction as `RetrievalQA` without the deprecation track; LCEL Runnables live underneath for free composability.

**Trade-offs accepted:** Tighter LangChain version coupling (we pin; dependabot for upgrades). Breaking-change exposure on minor LangChain releases (historical: 2–3/year).

**Reversibility:** **Moderate** — retriever (D2) and LLMClient (D4) stay as clean adapter boundaries; framework swap remains practical.


---

### Decision 7 — Backend language and framework

**Question:** Language + framework + API style?

**Options:**
- A — Python + FastAPI: a common production default; strong ecosystem for async APIs.
- B — Node + NestJS / Hono: same lang as frontend; weaker GenAI ecosystem.
- C — Go: extreme throughput; this app isn't gateway-bound; gap detour.
- D — Python + Litestar: faster than FastAPI; smaller ecosystem.

**Decision:** **Python + FastAPI**, REST + SSE for streaming, Pydantic v2 at every boundary, asyncio throughout.

**Reasoning:** Strongest language; ecosystem fit (LangChain, sentence-transformers, RAGAS); SSE handles streaming UX cleanly; Pydantic ties into structured LLM outputs naturally.

**Trade-offs accepted:** Slight perf ceiling vs Go/Litestar — irrelevant at our scale.

**Reversibility:** **Hard.**


---

### Decision 8 — Frontend framework and streaming UX

**Question:** Frontend stack + how we handle streaming, cancellation, retry?

**Options:**
- A — Next.js App Router + React + TS + Tailwind + shadcn/ui (a common production default).
- B — Remix: smaller ecosystem.
- C — SvelteKit: lighter; outside the standard toolchain.
- D — Streamlit (current): not suitable for client-facing production.

**Decision:** **Next.js App Router + React + TypeScript + Tailwind + shadcn/ui.** Streaming: SSE token-by-token; AbortController for cancel; optimistic retry; skeleton + token render; stop button.

**Reasoning:** A common production default; shadcn/ui = production components without UI-vendor lock-in.

**Trade-offs accepted:** App Router has rough edges; bundle size larger than SvelteKit.

**Reversibility:** **Hard.**


**Primer — shadcn/ui:** Not an npm package — a CLI that copies pre-built, Tailwind-styled, accessible React components (button, dialog, form, toast, etc.) directly into the repo. You own the source. No version lock. Industry standard for production Next.js apps in 2026.

---

### Decision 9 — AuthN/AuthZ + multi-tenancy

**Question:** Auth provider, session model, multi-tenancy approach?

**Options:**
- A — Clerk (managed): drop-in UI, OAuth, MFA, 10k MAU free.
- B — Auth.js / NextAuth (self-host): no per-MAU fee, more code.
- C — AWS Cognito: free at scale, rough DX.
- D — Supabase Auth: pulls you toward Supabase as DB too.

**Decision:** **Clerk** with email/password + Google + Discord OAuth.

**Multi-tenancy model:** Each authenticated user IS a tenant. Per-tenant data isolation via `user_id` FK on every row + ACL-at-retrieval filter on every vector query (anime data is public, but the discipline is enforced). Orgs/teams: out of scope for v1.

**Reasoning:** Fastest to ship credible multi-tenant consumer auth. Free tier covers early SaaS (≤10k MAU = $0); past 10k MAU unit cost (~$0.02/MAU) is within budget. Engineering time is the scarce resource, not the auth subscription.

**Trade-offs accepted:** Vendor coupling (mitigated: Clerk → Auth.js is a known community migration). Per-MAU line item.

**Reversibility:** **Moderate** — provider migration is a real but bounded effort. Trigger: Clerk >$200/mo (~70k MAU) → migrate to Auth.js.


**Primer — Clerk:** Managed auth-as-a-service with first-class Next.js integration (`<SignIn/>`, `<UserButton/>`, `auth()` server helper). You bring your own database; Clerk owns the identity layer. 10-minute setup.

---

### Decision 10 — Caching strategy

**Question:** What do we cache, where, how do we invalidate?

**Decision:** **Redis (ElastiCache)** — three logical caches:
1. **Response cache** — exact query string → cached answer. TTL 24h. Key: `resp:{user_id_or_anon}:{sha256(query)}`.
2. **Semantic cache** — query embedding → cached answer if cosine ≥ 0.92 vs a recent query. TTL 24h.
3. **Embedding cache** — text hash → embedding vector. No TTL.

**Reasoning:** Targets the 30%+ cache-hit-rate cost assumption. Semantic cache typically delivers 15–30% hit rate on consumer query paraphrases. **After D5 revision, embedding cache also serves latency** (not just cost — every cache hit saves the 50–100 ms OpenAI network call).

**Trade-offs accepted:** Cache-invalidation complexity on corpus changes (bust response/semantic on corpus version increment). Wrong-cache-hit risk on personalized paths — mitigated by `user_id` in key.

**Reversibility:** **Easy.**

---

#### ⚠️ REVISION (2026-07-14): the semantic cache was REMOVED, not tuned

The semantic cache never returned a single hit in production, and measurement showed
it could not be made to hit *safely*. Cosine over `text-embedding-3-small`, on labelled
query pairs:

| pair class | cosine range |
|---|---|
| genuine paraphrases (**should** hit) | 0.656 – **0.838** |
| meaning-inverted near-misses (**must not** hit) | 0.470 – **0.863** |

| example pair | cosine |
|---|---|
| `"anime with a strong female lead"` vs `"...strong male lead"` | **0.863** |
| `"romance anime with a happy ending"` vs `"...with a sad ending"` | **0.842** |
| best genuine paraphrase, for comparison | 0.838 |

**The near-misses score higher than the paraphrases.** No threshold exists that admits
one real paraphrase without also admitting "male lead" as the answer to "female lead".
At 0.92 the cache was safe and inert; lowering it to reach the assumed "15–30% hit rate"
would have started serving *wrong answers*. A slow correct answer costs two seconds; a
fast wrong one costs trust.

Retrieval overlap doesn't rescue it either (paraphrases overlap@10 down to 0.40, while
the female/male-lead pair overlaps 0.50). The root cause is not a bad threshold: embeddings
encode **topical** similarity, not **logical polarity**. "Happy ending" and "sad ending"
are topically near-identical.

The original trade-off line above — *"wrong-cache-hit risk … mitigated by `user_id` in key"* —
was simply wrong. A `user_id` scopes the cache per user; it does nothing about the same user
being handed the answer to a different question.

**What replaced it:** the response cache now hashes a **normalized** query (NFKC, casefold,
punctuation and whitespace collapsed — nothing that can change meaning: no stemming, no
stopword removal, no reordering). Measured live: `"Give me a gritty cyberpunk noir anime"`
4629 ms → the same request with different punctuation/casing **72 ms and 59 ms** (~65–78×),
while `"strong female lead"` vs `"strong male lead"` correctly **both run the full pipeline**.

**If a semantic cache is ever wanted back**, it needs an equivalence check embeddings
cannot provide — e.g. a cheap LLM judge on the candidate pair (~$0.000004 and ~300 ms,
versus ~$0.0004 and ~2.5 s for the generation it would save). That is a defensible design.
Cosine alone is not.


---

### Decision 11 — Queue and async work **[REVISED 2026-05-26]**

**Question:** Background-job system?

**Options:**
- A — ARQ (async Redis) + SQS: two systems.
- B — Celery + Redis: sync model, mismatch with async FastAPI.
- C — SQS + dedicated EKS worker Deployments (KEDA on queue depth): one queue system.
- D — Pure SQS + Lambda: serverless; duration limits, harder local dev.
- E — Temporal: overkill.

**Decision:** **C — SQS + EKS workers** (KEDA autoscale on `ApproximateNumberOfMessages`). ARQ removed; Redis stays scoped to caching only.

**Worker design:** Python long-running pods using `aiobotocore` long-poll (20s). Each pod handles N messages in parallel via asyncio. KEDA `ScaledObject` per queue (target = 10 msgs/worker; min 1, max 20). DLQ per main queue. Idempotency keys; at-least-once safe.

**Job categories:** `ingestion-queue` (corpus updates, re-embed), `feedback-queue` (thumbs processing, online eval sampling), `housekeeping-queue` (cost rollups, GDPR deletion).

**Reasoning:** One queue system materially simpler than two. SQS is the right tool for the heavy stuff (re-embed, deletion jobs); for lightweight thumbs feedback the sub-second SQS latency overhead is irrelevant (fire-and-forget). Redis cleanly scoped to caching.

**Trade-offs accepted:** SQS latency on lighter tasks; LocalStack added to docker-compose for dev parity.

**Reversibility:** **Easy.**


**Primer — KEDA:** Kubernetes Event-Driven Autoscaler — extends HPA with event-source-based metrics (SQS depth, Kafka lag, etc.). For SQS, `ScaledObject` CRD points at queue + worker Deployment; KEDA scales replicas on depth.

**Primer — LocalStack:** Local AWS emulator (SQS/S3/Secrets Manager/etc.) as Docker containers — lets docker-compose dev parity work without a real AWS account. Free tier covers everything we need.

---

### Decision 12 — Inference serving

**Question:** Hosted vs self-hosted; if hosted, which?

**Options:**
- A — Groq hosted API: fastest TTFT; pay-per-token.
- B — AWS Bedrock: AWS-native, slower TTFT.
- C — vLLM self-host on EKS GPU: control + cost at very high QPS; bad economics below ~150 QPS to a single model.
- D — SageMaker endpoints: managed self-host; most expensive AWS-native.

**Decision:** **Groq hosted API** (primary), **OpenAI** (fallback per D4). Self-hosted vLLM **added as an optional third venue per D4b** (2026-09-12), shipped dark behind a feature flag.

**Reasoning:** At 100k MAU with 30%+ cache hit, our call volume is well within Groq's rate envelope and cost ceiling. Self-host GPU economics only pay at sustained >~150 QPS to one model.

**Trade-offs accepted:** Vendor concentration risk on Groq (mitigated by OpenAI fallback).

**Reversibility:** **Moderate** — `LLMClient` interface is the abstraction. Trigger: sustained Groq cost >$2k/mo OR SLA misses → vLLM.

**[AMENDED 2026-09-12 by D4b]** The "self-host only above ~150 QPS" reasoning was a *cost* argument and remains valid for that question. It was also read as an implicit *capability* claim — that self-hosting could not meet our latency needs at small scale. S19/S20 measured that and found the opposite: vLLM serves this workload at 38 ms TTFT / 67.9 tok/s, inside every NFR by 20–45×. Self-hosting is therefore gated on operational readiness (HA, GPU node group, cost attribution), not on QPS. See `docs/GPU_VENUE.md`.


---

### Decision 13 — Observability stack

**Question:** App-level + LLM-specific observability + backend?

**Options:**
- A — OTel → Grafana Cloud (free) + Langfuse (self-host): portable, OSS LLM obs.
- B — LangSmith (managed): vendor, paid.
- C — Datadog: best DX, blows budget.
- D — Full self-hosted (Prom+Graf+Loki+Tempo+Langfuse): $0 software, ops burden.
- E — CloudWatch only: terrible for distributed traces + no LLM specifics.

**Decision:** **A — OpenTelemetry SDK → Grafana Cloud (free tier) for metrics/logs/traces + Langfuse (self-host on EKS) for LLM tracing & eval.**

**Reasoning:** OTel keeps backend choice portable. Grafana Cloud free fits our scale (10k series, 50 GB logs/mo). Langfuse self-host gives full LLM trace UX (per-request cost/latency/token breakdown, prompt registry, eval datasets).

**Trade-offs accepted:** Self-host Langfuse adds ~3 pods (postgres + clickhouse + app). Mitigated by mature Helm chart.

**Reversibility:** **High** — OTel is the affordance for backend swaps.

**Trigger to revisit:** Grafana free tier exceeded → paid tier or self-host.


**Primer — Langfuse:** OSS LLM-observability platform (LangSmith category, OSS + self-hostable). Every LLM call gets a trace with prompt/response/tokens/cost/latency; built-in prompt registry; eval datasets. Helm chart deploy.

**Primer — OpenTelemetry (OTel):** Vendor-neutral instrumentation standard for traces, metrics, logs. Instrument once (`opentelemetry-instrumentation-fastapi`); export anywhere. The non-negotiable foundation for not being locked into a vendor on observability.

---

### Decision 14 — Cloud provider and core services

**Question:** Cloud + service mapping?

**Options:**
- A — AWS: broadest managed-service coverage.
- B — GCP: best networking, gap detour.
- C — Azure: best MS ecosystem, gap detour.
- D — Multi-cloud: 1-engineer ops nightmare.

**Decision:** **AWS**, single region **us-east-1**.

**Service mapping:**
| Role | AWS service |
|---|---|
| Compute | EKS (D15) |
| Primary DB | RDS PostgreSQL (D1) |
| Cache / Redis | ElastiCache (D10) |
| Queue | SQS (D11) |
| Object storage | S3 |
| Secrets | Secrets Manager (D17) |
| DNS | Route 53 |
| TLS | ACM |
| CDN | CloudFront |
| WAF / rate limit | AWS WAF |
| Encryption | KMS |
| Container registry | ECR |
| Logs / metrics entry | CloudWatch → OTel → Grafana Cloud |

**Reasoning:** Single cloud = single IAM model = manageable for a small team. single-cloud keeps the operational model simple.

**Trade-offs accepted:** Egress to Grafana Cloud + OpenAI is real but small.

**Reversibility:** **Hard.**

**Trigger to revisit:** EU MAU >10% of total → consider eu-west-1 secondary region.


---

### Decision 15 — Container, orchestration, IaC

**Question:** Docker, K8s flavor, packaging, IaC?

**Pre-locked:** K8s/EKS.

**Decision:**
- **Docker** multi-stage; non-root user; healthcheck.
- **EKS** with managed node groups (2× t3.medium dev/staging, m6i.large prod).
- **Helm** for app packaging (a common production default; community charts for Postgres, Redis, ArgoCD, Langfuse all first-class).
- **Terraform** modular: `vpc`, `eks`, `rds`, `elasticache`, `s3`, `iam`, `secrets`, `app`.

**Reasoning:** Helm + Terraform + EKS are mature, well-documented tools. Multi-stage Dockerfile fixes a real `demo/` flaw.

**Trade-offs accepted:** EKS control-plane cost (~$73/mo even idle) accepted for the production-K8s skill build.

**Reversibility:** **Hard.**


---

### Decision 16 — CI/CD

**Question:** Tool, stages, environments, promotion, rollback?

**Decision:**
- **GitHub Actions** for CI; **ArgoCD** GitOps for K8s deploys; **Argo Rollouts** for canary; **Trivy** for image scan.
- **Pipeline stages (PR):** lint (`ruff`/`eslint`) → typecheck (`mypy`/`tsc`) → unit → integration (PG + Redis service containers) → build images → Trivy scan → push to ECR → ArgoCD auto-sync to staging → **RAGAS eval gate** blocks regression → manual approve → ArgoCD reconciles prod with Argo Rollouts canary (5% → 25% → 100% over 30 min) → smoke test → auto-rollback on SLO violation.
- **Environments:** dev (local docker-compose), staging (EKS namespace), prod (EKS namespace). Same cluster, separate namespaces with ResourceQuotas + NetworkPolicies.
- **Rollback:** Argo Rollouts undo + DB migration revert plan per migration.

**Reasoning:** Every component is in the standard toolchain except Argo Rollouts. The eval gate is a hard CI requirement.

**Trade-offs accepted:** Shared cluster staging+prod requires careful ResourceQuotas.

**Reversibility:** **Moderate.**


**Primer — Argo Rollouts:** ArgoCD's progressive-delivery sibling. Replaces a K8s Deployment with a Rollout resource that does canary/blue-green with automatic analysis (query Prometheus, fail rollout if metrics breach). ~30-min learning curve given ArgoCD background.

---

### Decision 17 — Secrets and configuration management

**Question:** Where secrets live, how they reach pods, how they rotate, how config differs per env?

**Decision:**
- **AWS Secrets Manager** is source of truth (DB passwords, Groq/OpenAI/Clerk keys, HF tokens, Langfuse keys).
- **External Secrets Operator (ESO)** in EKS syncs Secrets Manager → K8s Secrets; pods consume normally.
- **Helm values** per env (`values-{dev,staging,prod}.yaml`). Config split: build-time = Helm; runtime non-secret = ConfigMap; runtime secret = ESO.
- **Rotation:** RDS automated (Secrets Manager native); API-key rotation documented; manual for v1.

**Reasoning:** Industry-standard pattern for K8s + AWS Secrets Manager.

**Trade-offs accepted:** ESO is one more cluster operator (Helm chart, ~5 min install).

**Reversibility:** **Easy.**


**Primer — External Secrets Operator (ESO):** Cluster operator that watches `ExternalSecret` CRDs and materializes K8s Secrets by pulling from AWS Secrets Manager (or Vault, GCP SM). Declarative manifests reference Secrets Manager without baking secrets into Helm.

---

### Decision 18 — Security posture (threat model + mitigations)

**Threats:**
1. Prompt injection via retrieved anime synopsis.
2. Jailbreak attempts in user queries.
3. PII leakage in logs (email, queries — query history is PII per GDPR).
4. Multi-tenant data crossover.
5. Cost-DoS by malicious users.
6. Standard web attacks (XSS, CSRF, SQLi).
7. **(D5 addition)** OpenAI data egress for query embeddings.

**Mitigations:**
- Treat retrieved content as untrusted text (system prompt explicit).
- Structured output enforcement (Pydantic schema; reject non-matching).
- Prompt-injection canaries in eval set.
- Structured logger drops `email`, `query` by default; debug logs gated behind env flag + IAM.
- ACL-at-retrieval on every vector query (`user_id` filter); enforced even though anime data is public — discipline pattern.
- Per-user rate limits: AWS WAF (edge) + `slowapi` token bucket + daily query cap in Postgres.
- Cost kill switch (D20).
- Parameterized queries (SQLAlchemy), CSRF (Next.js built-in), CSP, HSTS, TLS everywhere.
- PII redaction before embedding (strip emails/names from query text before OpenAI call).
- OpenAI "data not used for training" setting enabled; privacy policy discloses sub-processor.
- mTLS service-to-service: deferred to v1.x (Linkerd/Istio); v1 uses K8s NetworkPolicies + IRSA.

**Reasoning:** Each threat real; each mitigation cheap individually. Layering is the point.

**Reversibility:** **Easy** — each mitigation is independent.

**Trigger to revisit:** SOC 2 audit pursued → escalate posture.


---

### Decision 19 — Evaluation strategy

**Decision:**
- **Offline golden set:** ~100 hand-curated `(query, expected_anime_ids)` pairs covering clear matches, vague preferences, edge cases, prompt-injection canaries. Versioned in `packages/eval/golden_sets/`.
- **Metrics:** RAGAS (faithfulness, answer_relevancy, context_precision, context_recall) + custom (diversity, grounding, refusal correctness).
- **CI gate:** RAGAS scores must not regress >3% vs `main` baseline; blocks merge.
- **Online:** 5% sample of prod queries scored async by `gpt-4o-mini` judge; results to Langfuse; drift alerts.
- **A/B:** prompt/model variants behind feature flag in Postgres table (v1); LaunchDarkly if it grows.
- **Regression in CI:** prompt-change PRs run full golden set; diff in PR comment.

**Reasoning:** Eval is the single biggest difference between "a demo" and "production system you can trust." It is the highest-leverage investment in production trustworthiness.

**Trade-offs accepted:** Golden-set maintenance ~30 min/week. LLM-as-judge online sampling cost ~$30/mo at 100k MAU.

**Reversibility:** **Easy** — additive.


**Primer — RAGAS:** Python lib (`pip install ragas`) of standardized RAG-quality metrics. Give it (question, retrieved_contexts, generated_answer, ground_truth); returns scores 0–1. Industry standard since ~2024.

**Primer — DeepEval:** RAGAS-adjacent with CI-native UX (pytest-style assertions). RAGAS covers our core needs; DeepEval flagged for awareness if we want pytest-integration later.

---

### Decision 20 — Cost controls

**Decision (layered):**
1. **Per-request token budget** in `LLMClient` — refuse oversized prompts.
2. **Model routing** (cheap-first, escalate on confidence; D4).
3. **Per-user daily quota** — Postgres counter + Redis fast counter; 429 with Retry-After. Free tier: 20 queries/day.
4. **Per-tenant cost meter** — Langfuse traces → nightly rollup → `user_costs` table.
5. **Spend alerts** — CloudWatch billing alarms at 50/75/90% of monthly budget → SNS → email + Slack.
6. **Hard kill switch at 200%** — CloudWatch alarm → Lambda → feature flag `LLM_ENABLED=false` → graceful "service temporarily unavailable."

**Reasoning:** No single mitigation sufficient; hard kill switches are non-negotiable.

**Reversibility:** **Easy.**


---

### Decision 21 — Failure-mode and degradation strategy

**Decision (explicit per failure mode):**

| Failure | Fallback |
|---|---|
| Groq down / rate-limited | Auto-switch to OpenAI `gpt-4o-mini`; log + alert |
| Both LLM providers down | Cached "popular this week" + friendly message |
| Vector DB (pgvector) slow/down | Postgres FTS on `combined_info` |
| Vector DB + FTS down | Curated diversity sample (10 hand-picked, randomized) |
| Reranker fails / >200 ms | Skip reranker; raw vector results; alert |
| Retrieval returns nothing | "I don't have strong matches — try…" + diversity sample |
| Malicious/out-of-scope input | Pydantic rejection → "I can't help with that" |
| Cost kill switch tripped | Feature flag `LLM_ENABLED=false` → temporarily unavailable |
| Redis cache down | App continues without cache (cost degrades, correctness intact) |
| Postgres down | 503; cannot serve (hard dependency, accepted) |

**Patterns:**
- Circuit breakers (`pybreaker`) on Groq, OpenAI, Langfuse.
- Retries: exponential backoff + jitter, max 3 attempts.
- Idempotency keys on write operations.
- Timeouts everywhere: Groq 10s, OpenAI 15s, Redis 200ms, Postgres 2s.

**Reasoning:** Without explicit fallback per mode, "production-grade" is an empty claim.

**Reversibility:** **Easy** — each fallback independent.


**Primer — pybreaker:** Python implementation of Circuit Breaker. Wraps external call; opens after N consecutive failures, short-circuits to fallback for cooldown, periodic test with single call. Prevents cascading failures.

---

### Decision 22 — Repo structure and code organization

**Decision:** **Monorepo**, a conventional monorepo structure:

```
anime-recommender/
├── apps/
│   ├── web/                    # Next.js frontend (App Router)
│   └── api/                    # FastAPI: query+stream, ingestion endpoints
├── packages/
│   ├── core/                   # shared: schemas, LLMClient, VectorIndex, prompts
│   ├── retrieval/              # hybrid retrieval, reranker, MMR
│   ├── ingestion/              # data loader, chunker, embedder, indexer
│   └── eval/                   # golden sets, RAGAS runners, regression harness
├── infra/
│   ├── terraform/              # vpc, eks, rds, elasticache, s3, iam, secrets, app
│   └── k8s/                    # Helm charts, ArgoCD ApplicationSets, Rollouts
├── .github/workflows/          # ci.yml, eval-gate.yml, cd.yml
├── tests/                      # unit, integration, e2e, load (k6)
├── docs/                       # architecture, decision-log, runbooks, ADRs
├── docker-compose.yml
├── Makefile
└── README.md
```

**Reasoning:** Atomic PRs across frontend+backend+infra valuable for a small team; single CI.

**Trade-offs accepted:** Larger repo; cross-package deps managed via `uv` workspaces.

**Reversibility:** **Hard** once committed.


---

## Cascading implications (cross-decision)

| Source | Affects | Impact |
|---|---|---|
| D5 (OpenAI embeddings) | D10 (Caching) | Embedding cache promoted from "cost optimization" to **cost + latency critical path** |
| D5 | D14 (Cloud / residency) | Privacy policy must disclose OpenAI as US sub-processor; enable "data not used for training" |
| D5 | D17 (Secrets) | OpenAI API key required from day 1 (not just for fallback) |
| D5 | D18 (Security) | "OpenAI data egress" added to threat model; PII redaction before embedding |
| D6 (modern v1 chains) | App code | Use `create_retrieval_chain` + `create_stuff_documents_chain`, NOT `langchain_classic.RetrievalQA` |
| D11 (SQS only) | D15 (Local IaC) | **LocalStack** added to docker-compose for dev parity |
| D11 | D16 (Helm chart) | Worker Deployments + KEDA `ScaledObject`s added |

---

## Revision history

| Date | Decision | Change | Reason |
|---|---|---|---|
| 2026-05-26 | D5 | Embedding model: `all-MiniLM-L6-v2` → OpenAI `text-embedding-3-large` | User direction; top quality from day 1 |
| 2026-05-27 | D5 | Embedding model: `text-embedding-3-large` (3072-dim) → `text-embedding-3-small` (1536-dim) | Per-query p50 measured at 399 ms (RTT to OpenAI US ~200 ms structural floor); 300 ms gate failed. `text-embedding-3-small` reduces server-side processing ~100–150 ms, bringing p50 into WARN/PASS range. Re-evaluate during RAGAS eval RAGAS — revert to 3-large if context recall degrades. |
| 2026-05-26 | D6 | Orchestration: thin custom + LCEL → full LangChain v1 chain factories (modern, NOT classic) | User direction; leverage LangChain depth |
| 2026-05-26 | D11 | Queue: ARQ + SQS → SQS-only + EKS workers | User direction; one queue system; ARQ removed |
| 2026-05-27 | D3 | MMR λ tuned 0.7 → 0.85 (config-driven via `MMR_LAMBDA`) | Step 4 golden-eval showed λ=0.7 over-diversified, regressing recall@3 −0.050 on franchise queries while reranker improved rank-1 +0.091. Higher λ favors relevance. |
| 2026-05-27 | D5 | `text-embedding-3-small` **accepted** (quality A/B vs 3-large not run) | Step 4 baseline solid in absolute terms (success@3=0.818); user accepted on cost (5×) + latency rather than run the 3-large comparison. Open item: unproven relative to 3-large. |
| 2026-09-12 | **D4b added** | Self-hosted vLLM venue added as an optional third tier, dark behind `LLM_VENUE_ROUTING_ENABLED=false` | Measured, not estimated: vLLM serves this workload at 38.2 ms TTFT / 67.9 tok/s on an RTX 3060 — inside every NFR by 20–45×. SGLang benchmarked head-to-head under verified condition parity; vLLM chosen on operational cost (23 GB smaller image, faster cold start, 2.67× better TTFT p99), not speed (2.6% gap, inside N=20 noise). See `docs/GPU_VENUE.md`. |
| 2026-09-12 | D12 amended | "Self-host only above ~150 QPS" clarified as a *cost* argument, not a *capability* claim | The QPS threshold was being read as "self-hosting can't meet our latency needs at small scale." Measurement refuted that. Self-hosting is now gated on operational readiness (HA, GPU node group, cost attribution), not throughput. |

---

## Status

Requirements, NFRs, and the decisions above are locked; the system is
implemented against them. Commit messages reference the implemented decision(s)
where useful, e.g. `feat(retrieval): hybrid + reranker + MMR`.
