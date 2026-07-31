<div align="center">

# Anime Recommendation Engine — Conversational RAG for Anime Discovery

### Grounded Anime Recommendations from Natural-Language Taste

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async%20%2B%20SSE-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangChain](https://img.shields.io/badge/LangChain-chain%20factories-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](#-how-the-rag-pipeline-works)
[![LLM](https://img.shields.io/badge/LLM-Groq%20%E2%86%92%20OpenAI-412991?style=flat-square&logo=openai&logoColor=white)](#%EF%B8%8F-tech-stack)
[![pgvector](https://img.shields.io/badge/pgvector-Hybrid%20RAG-4169E1?style=flat-square&logo=postgresql&logoColor=white)](#-how-the-rag-pipeline-works)
[![Redis](https://img.shields.io/badge/Redis-2--Layer%20Cache-DC382D?style=flat-square&logo=redis&logoColor=white)](#-how-the-rag-pipeline-works)
[![Clerk](https://img.shields.io/badge/Auth-Clerk%20%C2%B7%20JWT-6C47FF?style=flat-square&logo=clerk&logoColor=white)](#-security)
[![Next.js](https://img.shields.io/badge/Next.js-15%20%2F%20React%2019-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![SQS](https://img.shields.io/badge/SQS%20%C2%B7%20KEDA-Async%20Workers-FF4F8B?style=flat-square&logo=amazonaws&logoColor=white)](#%EF%B8%8F-tech-stack)
[![Observability](https://img.shields.io/badge/OTel%20%C2%B7%20Langfuse%20%C2%B7%20Prometheus%20%C2%B7%20Grafana-Tracing-F46800?style=flat-square&logo=opentelemetry&logoColor=white)](#-security)
[![Docker](https://img.shields.io/badge/Docker-Compose%20%C3%973-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docker.com)
[![Kubernetes](https://img.shields.io/badge/K8s-Helm%20%E2%86%92%20EKS-326CE5?style=flat-square&logo=kubernetes&logoColor=white)](#-deployment)
[![Terraform](https://img.shields.io/badge/Terraform-VPC%2FEKS%2FRDS%2FSQS-7B42BC?style=flat-square&logo=terraform&logoColor=white)](#-deployment)

[🚀 Quick Start](#-quick-start) · [🧰 Make Commands](#-make-commands) · [✨ Features](#-features) · [🏗️ Architecture](#%EF%B8%8F-architecture) · [📡 API](#-api-reference) · [🐳 Deployment](#-deployment)

</div>

---

## 🌟 What Is This?

**Anime Recommendation Engine** is a full-stack, production-grade **conversational anime discovery engine**. You describe
what you're in the mood for in plain language — *"light-hearted school anime with a strong female
lead"*, *"a dark psychological thriller under 24 episodes"* — and it returns **three anime**, each
with a short plot summary and a grounded *"why this matches you"* explanation, streamed to your
browser token-by-token.

Under the hood it's an **advanced hybrid-retrieval RAG pipeline**: dense `pgvector` similarity +
Postgres full-text (BM25-style) search are fused, re-ranked by a cross-encoder, diversified with
MMR, and handed to a **tiered LLM gateway** (Groq → OpenAI, with circuit breakers) that writes the
explanation **grounded only in the retrieved corpus** — every recommendation is validated back to a
real anime, so the model annotates, it never invents titles. It is **multi-tenant from day one**
(Clerk auth + per-user data), streams over SSE, enforces **per-user quotas + a global cost kill
switch**, and is instrumented end-to-end (OpenTelemetry traces, Langfuse LLM cost/latency,
Prometheus/Grafana metrics). It ships with a **CI eval gate**, async SQS workers, and a full
local→cloud path (Docker → Helm/EKS → Terraform).

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Hybrid Retrieval** | Dense **`pgvector`** cosine + Postgres **full-text (`tsvector`) BM25-style** search, fused with reciprocal-rank fusion — catches lexical intent ("school", "mecha", "isekai") that dense-only blurs |
| 🎯 **Cross-Encoder Rerank + MMR** | Top-k candidates re-scored by a **`ms-marco-MiniLM-L-12-v2`** cross-encoder, then **MMR** diversified so you don't get three near-identical sequels |
| 💬 **Grounded, Streaming Explanations** | Structured `/v1/recommend` returns cards; **`/v1/recommend/stream`** streams the prose reason token-by-token (SSE). Every `mal_id` is **validated against the retrieved set** — hallucinated titles are dropped |
| 🚫 **Honest Refusal** | Out-of-scope asks (general knowledge, coding help, injection attempts) or genuine no-match return an empty result **with a reason** instead of three irrelevant anime — enforced by a dedicated refusal eval |
| 🔁 **Tiered LLM Gateway + Fallback** | **Groq `gpt-oss-20b` → Groq `llama-3.3-70b` (escalation) → OpenAI `gpt-4o-mini` (fallback)** behind per-provider **circuit breakers** + timeouts — a single-provider outage isn't a full outage |
| ⚡ **2-Layer Cache** | Redis **embedding cache** (skip the OpenAI round-trip) + **response cache** (normalized query key), version-scoped by `CORPUS_VERSION`. *(A cosine semantic cache was measured unsafe on this workload and removed — see [`.env.example`](.env.example).)* |
| 🔐 **Auth + Quotas + Cost Controls** | **Clerk** JWT (RS256 via JWKS, fail-closed) · per-user **daily quota** (`429` + `Retry-After`) · pre-LLM **token-budget guard** · per-tenant **cost meter** · global **kill switch** (`LLM_ENABLED=false`) |
| 🩹 **Graceful Degradation** | Every failure has a defined fallback: Groq down → OpenAI · both LLMs down → cached "popular" set · pgvector down → Postgres FTS · retrieval empty → curated sample · Redis down → cache-miss pass-through |
| 📨 **Async Workers (SQS + KEDA)** | Feedback / ingestion (re-embed) / housekeeping queues on SQS with **DLQ + redrive**, **idempotent** at-least-once processing, **KEDA** autoscaling on queue depth |
| 📊 **Full Observability** | One request = one **OpenTelemetry** trace (trace-id woven into structured JSON logs) → Prometheus/Grafana; **Langfuse** for per-call LLM token/cost/latency; **PII-redacted** logs |
| 📈 **CI Eval Gate** | IR metrics (NDCG / MRR / Recall / Success @1,@3 + diversity) on a 111-query golden set, with an eval gate (manual/dispatch) that WOULD block regressions
| 🐳 **Deploy-Ready** | Multi-stage **non-root** Docker (×3) · 3-tier compose mesh · **Helm** chart with **Argo Rollouts canary** + KEDA + **External Secrets** · **Terraform** (VPC/EKS/RDS/ElastiCache/S3/SQS/ECR/IRSA) · GitHub Actions with the eval gate |

---

## 🖼️ Screenshots

<div align="center">

### Landing Page
![Landing page](assets/screenshots/landing.png)
*The marketing/landing page (`apps/web` App Router).*

### Query & Streaming Recommendations
![Query and streaming recommendations](assets/screenshots/recommend.png)
*Ask in natural language → grounded recommendation cards → the "why it matches" explanation streams in below.*

### Langfuse
![Langfuse trace list](assets/screenshots/langfuse-traces.png)
![Langfuse trace detail](assets/screenshots/langfuse-trace-detail.png)
*Per-call LLM traces (latency, tokens, cost) and one call's full execution graph — the tiered LLM gateway traced end-to-end.*

### Real-time Monitoring
![Grafana API overview dashboard](assets/screenshots/grafana.png)
*Request rate, p95 latency, LLM spend, and per-model cost — OTel → Collector → Prometheus → Grafana.*

</div>

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│            CLIENT · Next.js 15 / React 19 / Tailwind + shadcn/ui          │
│   Marketing site · query UI · live SSE stream · history · account · Clerk │
│   BFF route handlers (/app/api/*) mint the Clerk JWT SERVER-SIDE and proxy │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  REST + SSE   (API base URL never in the browser)
┌───────────────────────────────┼──────────────────────────────────────────┐
│                        FastAPI  Backend  (async)                          │
│  POST /v1/recommend (structured, cached, persisted)                       │
│  POST /v1/recommend/stream (SSE)   GET /v1/history   POST /v1/feedback     │
│  DELETE /v1/account (RTBF)          GET /health   GET /ready               │
│  Clerk JWT (fail-closed) · per-user quota (429) · token guard · kill switch│
│  OTel spans + PII-redacted JSON logs                                      │
└──────┬────────────────────┬───────────────────────┬───────────────────────┘
       │                    │                       │
┌──────┼─────────┐  ┌───────┼──────────┐   ┌────────┼──────────────┐
│ Postgres 16    │  │  Redis (cache)   │   │ SQS (LocalStack/AWS)  │
│ + pgvector     │  │  L1 embeddings   │   │ feedback / ingestion  │
│ dense + FTS    │  │  L2 responses    │   │ / housekeeping        │
│ (hybrid RAG)   │  │  (version-scoped)│   │ DLQ + redrive · KEDA  │
│ users·history· │  └──────────────────┘   └────────┬──────────────┘
│ feedback·usage │                                  │ idempotent workers
└──────┬─────────┘                          (re-embed · eval signal · popular)
       │  candidates (dense ⊕ FTS → RRF)
┌──────┼──────────────────────────────────────────────────────────────────────┐
│  RETRIEVAL   cross-encoder rerank (ms-marco) → MMR diversify → top-3 context   │
│  → GROUND: every returned mal_id validated against the retrieved set          │
└──────┬─────────────────────────────────────────────────────────────────────────┘
┌──────┼─────────────────────────────────────────────────────────────────────────┐
│  LLM gateway · Groq gpt-oss-20b → Groq llama-3.3-70b → OpenAI gpt-4o-mini        │
│  circuit breakers + timeouts · token-budget guard · cost meter · kill switch     │
└──────────────────────────────────────────────────────────────────────────────────┘
  Observability: OpenTelemetry → Collector → Prometheus → Grafana · Langfuse (LLM cost)
```

### Request Flow

```
[User]  sign in (Clerk) → ask: "light-hearted school anime with a strong female lead"
   │
   ▼
POST /v1/recommend (or /recommend/stream) ──► auth (fail-closed) ──► quota check (429 if over)
   │
   ├─► response cache (normalized key)  →  hit? return · miss ↓
   ├─► hybrid retrieve: pgvector dense ⊕ Postgres FTS  →  reciprocal-rank fusion
   ├─► cross-encoder rerank (ms-marco) → MMR diversify → top-3 + context
   ├─► tiered LLM writes grounded reasons  →  validate every mal_id vs retrieved set
   ├─► structured: persist to query_history (per-user) + record usage/cost
   └─► stream: SSE  event:token … event:done   (structured call is the record)

   (Groq down → OpenAI · all LLMs down → cached popular · pgvector down → FTS · empty → sample)
```

---

## 🗂️ Project Structure

```
Anime-Recommendation-Engine/          
│                   
├── apps/
│   ├── api/        # FastAPI: /v1/recommend(+stream) /v1/feedback /v1/history /v1/account
│   │              # /health /ready · auth · quotas · cost meter · SSE · Dockerfile (CPU torch)
│   ├── web/        # Next.js 15 App Router · Clerk · BFF proxy · query/history/account + marketing
│   └── worker/     # SQS consumer: feedback / ingestion / housekeeping handlers · slim Dockerfile
├── packages/
│   ├── core/       # schemas · LLM client (tiered+fallback) · cache · embeddings · SQS/jobs
│   │              # quotas · cost meter · resilience (circuit breaker) · observability (OTel/Langfuse)
│   ├── retrieval/  # hybrid (dense+FTS+RRF) · cross-encoder reranker · MMR · LangChain chain · grounding
│   ├── ingestion/  # CSV loader · chunker · OpenAI embedder · pgvector indexer
│   └── eval/       # golden sets · IR metrics · RAGAS wiring · naive-vs-advanced comparator · refusal
├── infra/
│   ├── compose/    # docker-compose.{data,app,obs}.yml — the 3-tier local stack (one project)
│   ├── terraform/  # bootstrap (state) + modules (vpc·eks·rds·elasticache·s3·sqs·ecr·iam·secrets·monitoring)
│   ├── k8s/        # helm/anime-recommender (api Rollout + web + workers + KEDA + ESO + migrate hook)
│   │              # argocd/applicationset.yaml · workers/ (standalone reference)
│   └── observability/  # grafana provisioning · otel-collector-config.yaml
├── migrations/     # alembic 0001–0005 (schema · 1536-d embeddings · usage · account deletions · HNSW)
├── scripts/        # audit/ · chaos/ · backup/ · deploy/ · rtbf.py · dev_token.py · eval_promote.py
├── evals/baseline.json   # frozen IR metrics for the CI eval gate
├── tests/          # unit + integration (pytest) · e2e (Playwright) · load (k6, tests/load/reports/)
├── assets/screenshots/  # README screenshots (UI + Grafana/Langfuse observability)
├── docs/           # architecture · repo-setup · runbooks/ · hardening/ · deploy/ — kept private, not committed
├── data/anime_with_synopsis.csv           # MAL corpus — kept private, supply your own (see Quick Start)
├── Makefile · pyproject.toml · uv.lock · .env.example · docker-compose.yml
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python **3.13** · FastAPI (async) · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic · **uv** workspace |
| **Orchestration** | LangChain (modern chain factories, **not** deprecated `RetrievalQA`) · structured output · SSE streaming |
| **LLM** | **Groq `openai/gpt-oss-20b`** (primary) → Groq `llama-3.3-70b-versatile` (escalation) → OpenAI `gpt-4o-mini` (fallback) |
| **Embeddings** | OpenAI **`text-embedding-3-small`** @ **1536-d** |
| **Vector / RAG** | **pgvector** in Postgres 16 (HNSW index) · dense cosine **+ Postgres full-text (`tsvector`)** hybrid · reciprocal-rank fusion |
| **Reranker** | **`cross-encoder/ms-marco-MiniLM-L-12-v2`** (baked into the API image; bge-reranker-v2-m3 was A/B-tested and dropped — too slow on CPU) |
| **Diversify** | **MMR** (`MMR_LAMBDA` relevance/diversity trade-off) |
| **Primary DB** | **PostgreSQL 16 + pgvector** — users · anime corpus + chunks · query history · feedback · daily usage · account-deletion audit |
| **Cache** | Redis — **embedding** + **response** caches (version-scoped by `CORPUS_VERSION`) |
| **Queue / Workers** | **AWS SQS** (LocalStack locally) · **KEDA** autoscaling · DLQ + redrive · idempotent handlers |
| **Auth** | **Clerk** (RS256 via JWKS, fail-closed) · per-user daily quota + token-budget guard + cost kill switch |
| **Security** | PII log redaction · structural grounding (mal_id validated) · injection-aware prompts · IRSA least-privilege · NetworkPolicy |
| **Resilience** | Per-provider **circuit breakers** + timeouts · tiered LLM fallback · retrieval fallback (pgvector→FTS→sample) |
| **Observability** | OpenTelemetry → Collector → **Prometheus + Grafana** · **Langfuse** (LLM cost/latency) · structured JSON logs |
| **Eval** | IR metrics (NDCG/MRR/Recall/Success @1,@3 + diversity) · refusal eval · RAGAS wiring · **CI eval gate** |
| **Frontend** | Next.js **15** · React **19** · TypeScript · Tailwind · shadcn/ui · Clerk · BFF route handlers |
| **Deployment** | Docker (multi-stage, non-root ×3) · Helm (Argo Rollouts canary + KEDA + ESO) · Terraform · GitHub Actions |

---

## 🚀 Quick Start

> The repo is **driven by a `Makefile`**. The containerised stack is **three compose files under one
> Docker project** (`anime-recommender`) — a **data** tier, an **app** tier, and an **observability**
> tier — so tiers share one network and start independently. **Every host port + credential lives in
> `.env`** (a `1002–1019` scheme so the whole stack fits on one machine).

### Prerequisites
- **Python 3.13** and [`uv`](https://docs.astral.sh/uv/) (uv provisions the interpreter for you)
- **Docker + Docker Compose**
- **Node 22 + pnpm** (only for native web dev; the Docker path builds the web for you)
- An **`OPENAI_API_KEY`** — required (embeddings + the fallback LLM). `GROQ_API_KEY` is used for the
  primary/escalation tiers; `CLERK_*` keys are needed to actually sign in through the UI.

### 1 · Install & configure
```bash
git clone https://github.com/ghourimarti/Anime-Recommendation-Engine.git && cd Anime-Recommendation-Engine
uv sync                              # resolve the workspace (Python 3.13) + dev deps
cp .env.example .env                 # set OPENAI_API_KEY, GROQ_API_KEY, CLERK_* ; ports pre-set
```

### 2 · Quality gate
```bash
make check                           # ruff lint + mypy (strict) + pytest  → the green gate
# or individually: make lint · make typecheck · make test
```

### 3 · Run the full stack — **one command from scratch (recommended)**
```bash
make upv                             # FROM ZERO: wipe volumes → build → start all tiers
                                     #   → migrate schema → ingest corpus (embeds ~268 rows via OpenAI, ~$0.01)
make urls                            # print every UI URL + login (ports/creds from .env)
```
> `upv` is the cold-boot button (`downv` → `up` → `db-migrate` → `ingest`). Expect a few minutes on a
> cold machine; the observability tier's ClickHouse + Langfuse migrations continue for ~1–3 min after.

### 3-alt · Bring it up tier by tier
```bash
make db                              # tier 1 — data: postgres + redis + localstack
make db-migrate                      # alembic upgrade head
make ingest                          # load + embed the corpus into pgvector (needs OPENAI_API_KEY)
make app                             # tier 2 — build + start migrate + sqs-init + api + web + worker
make obs                             # tier 3 (optional) — otel-collector + Langfuse + Prometheus/Grafana
make urls                            # print every URL
```

### 3-alt2 · Native hot-reload dev
```bash
make db                              # data tier in Docker
make dev-api                         # FastAPI on :1005 (uvicorn --reload)   [terminal 1]
make dev-web                         # Next.js on :1006                       [terminal 2]
```

### 4 · Verify it's up
```bash
curl http://localhost:1005/health    # {"status":"ok"}
curl http://localhost:1005/ready     # {"status":"ready"}  (proves api → postgres)

TOKEN=$(make -s token)               # mint a short-lived Clerk-signed JWT for API calls
curl -X POST http://localhost:1005/v1/recommend \
  -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
  -d '{"query":"light hearted school anime with a strong female lead"}'
```
> Then open **http://localhost:1006** → sign in (Clerk) → ask a question → watch the recommendation
> cards render and the explanation stream in.

**Service map** (host ports from `.env`):

| Service | URL |
|---|---|
| 🖥 **Web** (Next.js) | http://localhost:1006 |
| 📡 **API** | http://localhost:1005 · docs http://localhost:1005/docs |
| 🎭 Langfuse (LLM traces) | http://localhost:1013 |
| 📊 Grafana (metrics) | http://localhost:1019 |
| 📈 Prometheus | http://localhost:1018 |
| 🧰 RedisInsight | http://localhost:1016 |
| 🗄 Postgres (app) | `localhost:1002` (db `anime`) |
| 🧱 Redis (app cache) | `localhost:1003` |
| ☁️ LocalStack (SQS/S3) | http://localhost:1004/_localstack/health |

---

## 🧰 Make Commands

Everything is driven by the `Makefile` (`make help` prints the full menu). The stack is three compose
files under one project; all targets read ports + secrets from `.env`.

### Stack lifecycle (Docker)

| Command | What it does |
|---|---|
| `make db` | **Tier 1 — data.** Postgres + Redis + LocalStack. |
| `make app` | **Tier 2 — the app.** Builds + starts migrate + sqs-init + API + web + worker. |
| `make obs` | **Tier 3 — observability.** OTel Collector + Langfuse + Prometheus + Grafana (~1–3 min cold). |
| `make up` | **Everything** — data + app + obs (16 services). |
| `make upv` | **FROM SCRATCH** — `downv` → `up` → migrate → ingest. The cold-boot button. |
| `make down` | Stop + remove containers. **Keeps** volumes (your corpus + history survive). |
| `make downv` | Down **and wipe volumes** — ⚠️ **DESTRUCTIVE**. |
| `make ps` / `make logs` / `make urls` | Status · tail logs · print every URL + login. |

### Local dev & database

| Command | What it does |
|---|---|
| `make dev-api` / `make dev-web` | Hot-reload API (`:1005`) / web (`:1006`) on the host (run `make db` first). |
| `make worker` | Run an SQS worker locally (`WORKER_QUEUE=feedback` by default). |
| `make sqs-init` | Create local SQS queues + DLQs in LocalStack. |
| `make db-migrate` / `make db-shell` | `alembic upgrade head` · open `psql` in the container. |

### Data, quality & eval

| Command | What it does |
|---|---|
| `make ingest` | Load + embed the corpus into pgvector. |
| `make retrieve QUERY=...` / `make recommend QUERY=...` | Retrieve top-3 · retrieve **and** generate grounded recs (CLI). |
| `make check` | **The green gate** — `lint` + `typecheck` + `test`. |
| `make eval` | Advanced-vs-naive IR eval on the golden set. |
| `make eval-gate` | CI gate — eval, then compare vs `evals/baseline.json` (blocks regression + requires lift). |
| `make eval-refusal` | Refusal eval — does it decline what it can't answer and still answer what it can? |

### Load, hardening & deploy

| Command | What it does |
|---|---|
| `make load-validate` | Syntax-check all k6 scripts (no k6 needed). |
| `make load-smoke` / `load-baseline` / `load-peak` / `load-ramp` / `load-stream` | k6 scenarios (need `K6_AUTH_TOKEN`; see [`tests/load/README.md`](tests/load/README.md)). |
| `make audit-secrets` / `audit-deps` / `audit-licenses` / `audit-all` | Supply-chain audits. |
| `make chaos-llm` / `chaos-pg` / `chaos-net` / `chaos-restore` | Chaos drills (stack must be up). |
| `make backup-dump` / `backup-restore DUMP=...` / `backup-drill` | Backup + restore-drill. |
| `make rtbf USER=<clerk-id> [DRY=0]` | Right-to-be-forgotten operator path (defaults to dry-run). |
| `make deploy-stage1` | Stage-1 local-Docker acceptance (cold start → migrate + ingest → smoke → backup drill). |

---

## 📋 Environment Variables

Copy `.env.example` → `.env`. **Only `OPENAI_API_KEY` is strictly required** to run the pipeline;
`GROQ_API_KEY` + `CLERK_*` are needed for the full experience. Host ports use a `1002–1019` scheme.
(The file is fully annotated — this is the essential subset.)

| Variable | Purpose | Required | Default / Example |
|---|---|---|---|
| `OPENAI_API_KEY` | Embeddings + fallback LLM | ✅ | `sk-...` |
| `GROQ_API_KEY` | Primary + escalation LLM tiers | ▲ recommended | `gsk_...` |
| `GROQ_DEFAULT_MODEL` | Primary model | – | `openai/gpt-oss-20b` |
| `GROQ_ESCALATION_MODEL` | Escalation (long/hard queries) | – | `llama-3.3-70b-versatile` |
| `OPENAI_FALLBACK_MODEL` | Availability fallback | – | `gpt-4o-mini` |
| `LLM_PRIMARY` | Which provider serves the first attempt | – | `groq` |
| `LLM_PRICING` | Source-of-truth cost table (USD/1M tokens) | – | JSON (see file) |
| `DATABASE_URL` | Postgres + pgvector DSN | ✅ | `postgresql+asyncpg://anime:anime@localhost:1002/anime` |
| `REDIS_URL` | Cache (unset → caching off, app still works) | – | `redis://localhost:1003/0` |
| `CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` | Clerk API auth | ▲ for UI login | `pk_test_...` / `sk_test_...` |
| `CLERK_JWKS_URL` | JWKS for RS256 verify (empty → auth fails closed, 503) | ▲ | *(empty)* |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Web Clerk key (inlined at **build** time) | ▲ for UI | `pk_test_...` |
| `API_BASE_URL` | BFF → API (docker overrides to `http://api:8000`) | – | `http://localhost:1005` |
| `RERANKER_MODEL` | Cross-encoder (must match the image's baked model) | – | `cross-encoder/ms-marco-MiniLM-L-12-v2` |
| `MMR_LAMBDA` | Relevance ↔ diversity trade-off | – | `0.85` |
| `QUOTA_FREE_TIER_DAILY` | Per-user daily request cap (over → 429) | – | `100` (dev) |
| `LLM_MAX_INPUT_TOKENS` / `LLM_MAX_OUTPUT_TOKENS` | Pre-LLM budget guard / output cap | – | `3000` / `1200` |
| `LLM_ENABLED` | Cost **kill switch** (`false` → serve fallback, no LLM) | – | `true` |
| `CORPUS_VERSION` | Bump after a re-ingest → invalidates caches | – | `v1` |
| `AWS_ENDPOINT_URL` | SQS/S3 endpoint (LocalStack locally) | – | `http://localhost:1004` |
| `SQS_QUEUE_PREFIX` / `SQS_MAX_RECEIVE_COUNT` | Queue prefix · DLQ redrive count | – | `anime-dev` / `5` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_SERVICE_NAME` / `OTEL_SDK_DISABLED` | Tracing export · service label · on/off | – | `http://localhost:1014` · `anime-rag-api` · `true` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` | LLM tracing (optional; degrades if unset) | – | `pk-lf-...` / `sk-lf-...` / `http://localhost:1013` |
| `LOG_LEVEL` / `CORS_ORIGINS` | HTTP-layer config | – | `INFO` · `["http://localhost:1006",...]` |

> **No real secret is committed.** `.env` is gitignored; production values live in AWS Secrets Manager
> and are synced into the cluster by the External Secrets Operator.

---

## 📡 API Reference

Base path for app endpoints is **`/v1`**. Health/readiness are unprefixed.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | – | Liveness (process up, no deps) |
| `GET` | `/ready` | – | Readiness (checks Postgres; `503` if not ready) |
| `POST` | `/v1/recommend` | ✅ | Structured, grounded recommendations — cached + persisted to per-user history |
| `POST` | `/v1/recommend/stream` | ✅ | **SSE** stream of the explanation (`event: token …` → `event: done`) |
| `POST` | `/v1/feedback` | ✅ | Thumbs up/down per recommendation (also enqueues an async eval-signal job) |
| `GET` | `/v1/history` | ✅ | Paginated per-user query history |
| `DELETE` | `/v1/account` | ✅ | Right-to-be-forgotten: deletes the caller's data (`204 No Content`) |

<sub>Auth is **fail-closed**: `/v1/*` require a valid Bearer JWT (Clerk in prod; a minted dev token
locally via `make token`). Missing/invalid → `401`; auth unconfigured → `503`. `/health` + `/ready`
stay open for probes. Over the per-user daily quota → `429` with `Retry-After`.</sub>

### Example: `POST /v1/recommend`
```json
POST /v1/recommend            Authorization: Bearer <token>
{ "query": "light hearted school anime with a strong female lead" }
```
```json
// 200 OK
{
  "query": "light hearted school anime with a strong female lead",
  "query_history_id": 42,
  "recommendations": [
    { "mal_id": 20583, "title": "Haikyuu!!",
      "summary": "A short but determined boy joins his high-school volleyball club...",
      "why_match": "Light-hearted school setting with an energetic ensemble and..." }
  ],
  "degraded": false,
  "notice": null
}
```
> On a declined/no-match request `recommendations` is empty and `notice` explains why (out-of-scope,
> injection attempt, or nothing in the corpus genuinely matched). On a degraded fallback,
> `degraded: true` and `notice` is set.

### Example: `POST /v1/recommend/stream` (SSE)
```
event: token
data: Haikyuu!! is a great fit — a light-hearted school club story with...

event: token
data:  an energetic cast and plenty of comedy between matches...

event: done
data: [DONE]
```

---

## 🧠 How the RAG Pipeline Works

1. **Authenticate + quota** — the Bearer JWT (Clerk, verified against JWKS) is checked fail-closed;
   its `sub` is the `user_id` that scopes history, feedback, usage, and the per-user daily quota
   (`429` over the cap). A pre-LLM **token-budget guard** rejects oversized inputs before spending.
2. **Cache** — the **response cache** (normalized query key, version-scoped by `CORPUS_VERSION`) is
   checked first; the **embedding cache** avoids re-embedding a repeated query.
3. **Ingest (offline / worker)** — the MAL CSV is loaded, chunked with structure-aware metadata,
   embedded with OpenAI `text-embedding-3-small` (1536-d), and upserted into `pgvector` (HNSW index)
   alongside a generated `tsvector` full-text column. Re-embedding runs as an SQS ingestion job.
4. **Hybrid retrieve** — dense `pgvector` cosine **and** Postgres full-text (BM25-style) search run in
   parallel and are fused with **reciprocal-rank fusion**, recovering lexical intent that dense-only
   retrieval blurs across similar synopses.
5. **Rerank + diversify** — the fused top-k is re-scored by a **`ms-marco-MiniLM-L-12-v2`
   cross-encoder**, then **MMR** trims it to a diverse top-3 (no three near-identical sequels).
6. **Generate (grounded)** — the tiered LLM writes a short reason per anime via LangChain structured
   output. The **product set is fixed by retrieval**: every returned `mal_id` is validated against the
   retrieved candidates — a hallucinated or wrong id is dropped (or recovered by title match), so
   injected synopsis text can't change *what* gets recommended. Streamed as SSE for the live view.
7. **Persist + observe** — the structured call persists the turn to `query_history` (per-user) and
   records tokens + cost in `usage_daily`; the whole request is one OpenTelemetry trace (trace-id in
   the JSON logs), LLM cost/latency to Langfuse, RED + cache metrics to Prometheus/Grafana. **PII is
   redacted from logs.**
8. **Degrade, never crash** — Groq down → OpenAI fallback; all LLMs down → cached "popular" set;
   pgvector slow/down → Postgres FTS; retrieval empty → curated diversity sample; Redis down →
   cache-miss pass-through; budget kill switch (`LLM_ENABLED=false`) → fallback with no LLM call.

---

## 🔒 Security

- **Authentication** — **Clerk** JWT verified **RS256 against the JWKS endpoint**, with a configurable
  clock-skew leeway. `/v1/*` are **fail-closed** (missing/invalid token → `401`, unconfigured auth →
  `503`); `/health` + `/ready` stay open for probes. The web tier uses a **BFF proxy**: the API base
  URL and the Clerk token are handled **server-side**, never exposed to the browser.
- **Multi-tenant isolation** — history, feedback, usage, and quotas are all keyed by the JWT subject;
  a user can only ever read their own data.
- **Grounding as injection defense** — the recommendation set is decided by **retrieval + ranking**,
  not the model; the LLM only authors *reasons*, and every `mal_id` is validated against the retrieved
  set, so text injected into a synopsis can't hijack the result. Prompts also treat retrieved content
  as untrusted.
- **PII hygiene** — a structured-log redactor scrubs sensitive fields (email, query text, tokens,
  etc.); prompt/response bodies aren't logged (token counts + cost only; full traces live in Langfuse).
- **Abuse + cost** — per-user **daily quota** (`429` + `Retry-After`), pre-LLM **token-budget guard**,
  per-tenant **cost meter**, and a global **kill switch**.
- **Right to be forgotten** — `DELETE /v1/account` plus an operator CLI (`make rtbf`) cascade-delete a
  user's rows with an audit record (`account_deletions` table, migration 0004).
- **Infrastructure** — IRSA roles scoped to **exact** SQS/S3/secret ARNs (no wildcards), private RDS +
  ElastiCache, KMS encryption, secrets only in AWS Secrets Manager (synced via ESO), and a default-deny
  NetworkPolicy per namespace.

---

## 🗄️ Database Schema

PostgreSQL 16 + pgvector (Alembic migrations `0001`–`0005`):

```
users               id (Clerk user_id, PK) · email · created_at
anime_titles        mal_id (PK, MAL natural key) · name · score · genres (JSON) · synopsis · created_at
anime_chunks        id (PK) · mal_id (FK→anime_titles, CASCADE) · chunk_index · text
                    · embedding vector(1536) · embedding_model · chunk_metadata (JSON)
                    · text_tsv (GENERATED tsvector, GIN)   ← the sparse half of hybrid search
                    · HNSW index on embedding              ← the dense half (migration 0005)
query_history       id (PK) · user_id (FK→users, SET NULL) · query · response (JSON) · created_at
feedback            id (PK) · user_id (FK) · query_history_id (FK, CASCADE) · mal_id · rating (±1) · created_at
usage_daily         (user_id, day) composite PK · query_count · input_tokens · output_tokens
                    · cost_usd NUMERIC(12,6) · updated_at      ← per-tenant cost meter (atomic UPSERT)
account_deletions   audit trail for right-to-be-forgotten requests (migration 0004)
```

> Vectors live **in Postgres** (`pgvector`), not a separate vector DB — one database to operate at this
> corpus size. Deleting a user is an explicit cascade across the per-user tables (RTBF).

---

## 📊 Results (real numbers, honest scope)

| Metric | Result |
|---|---|
| **Retrieval quality** | **NDCG@3 = 0.703 · MRR = 0.741 · Recall@3 = 0.746 · Success@3 = 0.851** (NDCG@1 = 0.653) — measured on a **111-query golden set** (101 scored + 10 adversarial), `evals/baseline.json` |
| **Diversity** | **distinct-ratio = 1.0** on the golden set (MMR yields all-distinct top-3) |
| **Answer-quality (RAGAS)** | RAGAS is **wired** (`packages/eval`) but **not run in the committed baseline** (`"ragas": null`) — an honest gap, not a claimed number |
| **Load** | **Sustained 50 RPS held** — 15,001 requests, ~0 failures (`tests/load/reports/`). *Scope: the sustained scenario exercises the cached/structured path; full-pipeline latency and the peak/ramp/stream scenarios are in [`tests/load/README.md`](tests/load/README.md).* |
| **Cost** | LLM-dominated; documented estimate **~$0.0004/request** with the tiered gateway (`.env.example`) — the `LLM_PRICING` table + per-tenant `usage_daily` meter make it auditable |
| **Quality gate** | `make check` = **ruff clean + mypy strict + pytest** green; **CI eval gate** blocks a merge on regression vs baseline **and** requires lift over naive |
| **Deploy** | **Local Docker verified** (3-tier compose builds + `/health` OK; `make deploy-stage1` acceptance) · **Helm** chart `helm lint` + `kubeconform` clean (dev/staging/prod) · **Terraform** `validate` clean — **authored, not applied** |

---

## 🐳 Deployment

A clean local → cloud path:

1. **Local Docker** — multi-stage **non-root** images (`api` with CPU-only torch, `web` Next standalone,
   slim `worker`) + the 3-tier compose mesh. `make up` / `make upv` bring up the whole stack; a
   one-shot `migrate` job gates the API; LocalStack provides SQS/S3.
   ```bash
   make deploy-stage1        # cold start → migrate + ingest → smoke → backup drill
   ```
2. **Helm** — one chart (`infra/k8s/helm/anime-recommender`): API as an **Argo Rollouts canary** with a
   Prometheus **AnalysisTemplate** (auto-rollback), web (Deployment + HPA), workers (Deployment + **KEDA
   ScaledObject** per queue), migrate as a pre-upgrade hook, **External Secrets** for AWS SM, IRSA
   ServiceAccounts, Ingress, ResourceQuota + NetworkPolicy.
   ```bash
   helm lint infra/k8s/helm/anime-recommender -f infra/k8s/helm/anime-recommender/values-dev.yaml
   helm template infra/k8s/helm/anime-recommender -f .../values-prod.yaml | kubeconform -ignore-missing-schemas
   ```
3. **Terraform** — modular **VPC · EKS · RDS(pgvector) · ElastiCache · S3 · SQS · ECR · IAM/IRSA ·
   Secrets/KMS · billing alarms**; S3 + DynamoDB remote-state via a `bootstrap`. `terraform validate`
   passes; **not applied** (apply is the cloud-deploy gate).
   ```bash
   cd infra/terraform/envs/dev && terraform init -backend=false && terraform validate
   ```
4. **GitOps + CI/CD** — an **ArgoCD ApplicationSet** stamps one Application per env from the chart;
   GitHub Actions (`.github/workflows/`) runs lint → mypy → tests → build → **eval gate** → chain, or footnote it as dispatch-only.

---

## 🗺️ Roadmap

Realistic next steps, grounded in what's deliberately deferred (Decision Log + `.env` notes):

- 📈 **Run + report RAGAS** — the harness is wired; capture faithfulness/answer-relevancy into the baseline.
- ☁️ **Apply the infra** — take Terraform `validate` → real `plan`/`apply` on EKS; wire the deployed endpoints.
- 🔁 **Re-open Groq as primary** — once Groq's tool-call validation is fixed, flip `LLM_PRIMARY=groq` (the eval + refusal gates guard the switch).
- 💳 **Billing** — the paid-tier UI is stubbed (`NEXT_PUBLIC_BILLING_ENABLED=false`); wire a real payment provider + quota tiers.
- 🧠 **Query enhancement** — multi-query / HyDE if eval shows recall is the bottleneck.
- ⚙️ **Self-hosted inference** — vLLM on an EKS GPU pool once sustained cost/QPS justifies it.
- 🌍 **Multi-region + i18n** — deferred in v1; revisit when EU MAU or non-English demand appears.

---

## 👤 About the Author

<div align="center">

Built by **Zain Ul Abdin** — a **Full-Stack AI / GenAI Engineer** who builds production-grade AI
systems **end to end**: not just the model, but the whole stack — RAG pipelines, agentic systems,
fine-tuned LLMs, inference serving, containerized deployment, CI/CD, and the observability that keeps
it healthy. **Anime Recommendation Engine** is a deployable service — with tests, an eval gate, security,
observability, and infrastructure-as-code.

</div>

### 🧩 What I Build
- 🔍 RAG & retrieval pipelines (embeddings, hybrid search, reranking, grounding, **evaluation**)
- 🤖 Agentic AI systems (LangChain · LangGraph · CrewAI — tool use, corrective loops)
- 🎛️ Full-stack AI apps & LLM-backed APIs (FastAPI · Next.js)
- ☁️ MLOps / LLMOps — Docker, Kubernetes, Helm, Terraform, CI/CD, observability
- 💰 Cost, evaluation & reliability engineering for LLM systems

### 🛠️ Tech I Work With
`Python` · `FastAPI` · `LangChain / LangGraph` · `PyTorch` · `Hugging Face` ·
`pgvector / Qdrant / FAISS / Chroma / Pinecone` · `OpenAI / Claude / Groq / LLaMA / Mistral` ·
`LoRA / QLoRA / SFT` · `Docker` · `Kubernetes` · `Helm` · `Terraform` ·
`GitHub Actions / ArgoCD` · `Prometheus / Grafana / Langfuse` ·
`AWS (EKS · RDS · ElastiCache · SQS · ECR · S3)`

