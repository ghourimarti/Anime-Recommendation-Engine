.PHONY: help sync test lint format typecheck check clean
.PHONY: ingest retrieve eval eval-gate eval-refusal recommend dev-api dev-web dev lf-models token
.PHONY: db-up db-migrate db-down db-shell
.PHONY: db app obs up down upv downv ps logs urls dev
.PHONY: obs-up obs-down obs-logs worker sqs-init
.PHONY: eval-compare eval-promote
.PHONY: load-validate load-smoke load-baseline load-peak load-ramp load-stream
.PHONY: audit-secrets audit-deps audit-licenses audit-all
.PHONY: chaos-llm chaos-pg chaos-net chaos-restore
.PHONY: backup-dump backup-restore backup-drill
.PHONY: rtbf
.PHONY: deploy-stage1-smoke deploy-stage1

# ╔══════════════════════════════════════════════╗
# ║  Layered docker stack                        ║
# ╚══════════════════════════════════════════════╝
#   db     = data tier         postgres + redis + localstack        (3 svc)
#   app    = data + app tier   + sqs-init + migrate + api + web + worker
#   obs    = observability     otel-collector + langfuse[web/worker/postgres/
#                              redis/clickhouse/minio]              (8 svc)
#   up     = db + app + obs     everything (16 svc)
#   down   = stop + remove containers          (KEEPS volumes)
#   downv  = down + wipe named volumes          (DESTRUCTIVE)
#   upv    = from scratch: downv → up → migrate → ingest (fully working app)
#
# All three compose files declare `name: anime-recommender`, so they share ONE
# docker project + network. The api container reaches langfuse-web/otel-collector
# by DNS when obs is up; when obs is down, telemetry is dropped silently.
#
# `--env-file .env` is passed EXPLICITLY: with compose files in infra/compose/,
# docker compose does NOT auto-load `.env` from CWD. Skipping it makes the web
# build bake the fallback (empty Clerk key) into the client bundle.
COMPOSE_DIR := infra/compose
DC_ENV      := --env-file .env
DC_DATA     := docker compose $(DC_ENV) -f $(COMPOSE_DIR)/docker-compose.data.yml
DC_APP      := docker compose $(DC_ENV) -f $(COMPOSE_DIR)/docker-compose.data.yml -f $(COMPOSE_DIR)/docker-compose.app.yml
DC_OBS      := docker compose $(DC_ENV) -f $(COMPOSE_DIR)/docker-compose.obs.yml
DC_FULL     := docker compose $(DC_ENV) -f $(COMPOSE_DIR)/docker-compose.data.yml -f $(COMPOSE_DIR)/docker-compose.app.yml -f $(COMPOSE_DIR)/docker-compose.obs.yml

# ─── Ports (must mirror the PORTS section in .env — make does not parse .env;
# override per-invocation: `make dev-api API_PORT=9000`) ───────────────────
POSTGRES_PORT          ?= 1002
REDIS_PORT             ?= 1003
LOCALSTACK_PORT        ?= 1004
API_PORT               ?= 1005
WEB_PORT               ?= 1006
CLICKHOUSE_HTTP_PORT   ?= 1007
CLICKHOUSE_NATIVE_PORT ?= 1008
LANGFUSE_POSTGRES_PORT ?= 1009
LANGFUSE_REDIS_PORT    ?= 1010
MINIO_API_PORT         ?= 1011
MINIO_CONSOLE_PORT     ?= 1012
LANGFUSE_WEB_PORT      ?= 1013
OTEL_GRPC_PORT         ?= 1014
OTEL_HTTP_PORT         ?= 1015
REDISINSIGHT_PORT      ?= 1016
OTEL_PROM_PORT         ?= 1017
PROMETHEUS_PORT        ?= 1018
GRAFANA_PORT           ?= 1019

# Credentials shown in `make urls` (mirror the CREDENTIALS section in .env).
LANGFUSE_INIT_USER_EMAIL    ?= admin@anime.local
LANGFUSE_INIT_USER_PASSWORD ?= anime-admin-1234
MINIO_ROOT_USER             ?= minio
MINIO_ROOT_PASSWORD         ?= miniosecret
LANGFUSE_REDIS_AUTH         ?= langfuse
GRAFANA_ADMIN_USER          ?= admin
GRAFANA_ADMIN_PASSWORD      ?= admin

help:
	@echo "Full run-from-scratch guide: docs/run-from-scratch.md"
	@echo ""
	@echo "── Docker stack (tiered; ports + creds in .env) ──────────────────────"
	@echo "  make db         data tier only     (postgres + redis + localstack)"
	@echo "  make app        data + app tier    (+ migrate + api + web + worker)"
	@echo "  make obs        observability      (langfuse + otel; ~1-3min cold start)"
	@echo "  make up         EVERYTHING         (db + app + obs, 16 services)"
	@echo "  make upv        FROM SCRATCH       (downv → up → migrate → ingest)"
	@echo "  make down       stop + remove      (KEEPS volumes)"
	@echo "  make downv      down + WIPE volumes (DESTRUCTIVE)"
	@echo "  make ps|logs|urls   status | tail logs | print all URLs"
	@echo ""
	@echo "── Local dev (hot reload; run 'make db' first) ───────────────────────"
	@echo "  make dev-api    FastAPI on :$(API_PORT)  (uvicorn --reload)"
	@echo "  make dev-web    Next.js on :$(WEB_PORT)"
	@echo "  make worker     run an SQS worker    (WORKER_QUEUE=feedback)"
	@echo "  make sqs-init   create local SQS queues + DLQs in LocalStack"
	@echo ""
	@echo "── Database ──────────────────────────────────────────────────────────"
	@echo "  make db-up      start ONLY postgres (waits for healthy)"
	@echo "  make db-migrate alembic upgrade head"
	@echo "  make db-down    stop the postgres container"
	@echo "  make db-shell   open psql in the running container"
	@echo ""
	@echo "── Observability ─────────────────────────────────────────────────────"
	@echo "  make obs-down   stop the observability tier"
	@echo "  make obs-logs   tail Langfuse web + worker logs"
	@echo ""
	@echo "── Workspace ─────────────────────────────────────────────────────────"
	@echo "  make sync       uv sync (resolve workspace + dev deps)"
	@echo "  make test       run all tests"
	@echo "  make lint | format | typecheck"
	@echo "  make check      lint + typecheck + test"
	@echo "  make clean      remove caches"
	@echo ""
	@echo "── Domain (RAG pipeline) ─────────────────────────────────────────────"
	@echo "  make ingest              load + embed the corpus"
	@echo "  make retrieve QUERY=...   retrieve top-3 for a query"
	@echo "  make recommend QUERY=...  retrieve + generate grounded recs"
	@echo "  make eval                 advanced-vs-naive golden eval"
	@echo "  make eval-compare         gate eval_report.json vs evals/baseline.json"
	@echo "  make eval-promote         bump evals/baseline.json from eval_report.json"
	@echo ""
	@echo "── Load testing (see tests/load/README.md) ───────────────────────────"
	@echo "  make load-validate  syntax-check all k6 scripts (no k6 needed)"
	@echo "  make load-smoke | load-baseline | load-peak | load-ramp | load-stream"
	@echo ""
	@echo "── Hardening: audits / chaos / backups / compliance / deploy ─────────"
	@echo "  make audit-secrets | audit-deps | audit-licenses | audit-all"
	@echo "  make chaos-llm | chaos-pg | chaos-net | chaos-restore   (needs stack up)"
	@echo "  make backup-dump | backup-restore DUMP=path | backup-drill"
	@echo "  make rtbf USER=<clerk-user-id> [DRY=0]   RTBF operator path (default dry-run)"
	@echo "  make deploy-stage1-smoke | deploy-stage1"

# ╔══════════════════════════════════════════════╗
# ║  Workspace targets                           ║
# ╚══════════════════════════════════════════════╝
sync:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run mypy

check: lint typecheck test

clean:
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .mypy_cache .ruff_cache
	@echo "Caches removed."

# ╔══════════════════════════════════════════════╗
# ║  Tiered docker stack                         ║
# ╚══════════════════════════════════════════════╝
# Bring up one tier at a time, or the whole thing. See the DC_* variables and
# the "Layered docker stack" comment at the top of this file.

db:            ## data tier only: postgres + redis + localstack
	$(DC_DATA) up -d
	@echo "Data tier up: postgres :$(POSTGRES_PORT), redis :$(REDIS_PORT), localstack :$(LOCALSTACK_PORT)."

app:           ## data + app tier: + migrate + sqs-init + api + web + worker
	$(DC_APP) up --build -d
	@echo "App tier up: api http://localhost:$(API_PORT)  |  web http://localhost:$(WEB_PORT)"

obs:           ## observability tier: langfuse + otel (heavy; ~1-3min cold start)
	$(DC_OBS) up -d
	@echo ""
	@echo "  Observability up — first cold start ~1-3 min (ClickHouse + Langfuse migrations)."
	@echo "  Langfuse UI: http://localhost:$(LANGFUSE_WEB_PORT)  (first run: sign up → create org → copy pk-lf/sk-lf into .env)"
	@echo "  OTel Collector: localhost:$(OTEL_GRPC_PORT) (gRPC) | localhost:$(OTEL_HTTP_PORT) (HTTP)"
	@echo "  Then set OTEL_SDK_DISABLED=false in .env and restart the api (make app)."

up:            ## EVERYTHING: db + app + obs (16 services), then print all URLs
	$(DC_FULL) up --build -d
	@echo ""
	@echo "  Waiting for the API to report healthy (up to 60s)…"
	@for i in $$(seq 1 30); do \
	    if curl -sf -o /dev/null http://localhost:$(API_PORT)/health 2>/dev/null; then break; fi; \
	    sleep 2; \
	done
	@echo "  Note: Langfuse cold start can take 1-3 min more (ClickHouse + migrations)."
	@echo "  First-ever run also needs 'make db-migrate' + 'make ingest' (or use 'make upv')."
	@$(MAKE) --no-print-directory urls

down:          ## stop + remove all containers (KEEPS named volumes)
	$(DC_FULL) down

downv:         ## down + WIPE named volumes — DESTROYS corpus, traces, Langfuse org
	$(DC_FULL) down -v

# FROM SCRATCH in one command: wipe → build volumes + all containers → wait for
# postgres → migrate schema → ingest corpus. Leaves a fully working, queryable
# app. Ingest embeds ~268 rows via OpenAI (~$0.01; needs OPENAI_API_KEY).
upv:           ## from scratch: downv → up → migrate → ingest (fully working app)
	@echo "─── upv: wiping volumes + rebuilding from scratch ──────────────"
	$(DC_FULL) down -v
	$(DC_FULL) up --build -d
	@echo "─── waiting for postgres to accept connections ─────────────────"
	@until $(DC_DATA) exec -T postgres sh -c 'pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB' >/dev/null 2>&1; do sleep 1; done
	@echo "─── migrate schema (host alembic → localhost:$(POSTGRES_PORT)) ──"
	$(MAKE) db-migrate
	@echo "─── ingest corpus (embeds via OpenAI) ──────────────────────────"
	$(MAKE) ingest
	@echo ""
	@echo "  upv complete — full stack up, schema migrated, corpus ingested."
	@echo "  Web: http://localhost:$(WEB_PORT)   API: http://localhost:$(API_PORT)/health"
	@$(MAKE) --no-print-directory urls

ps:            ## status of every container in the stack
	$(DC_FULL) ps

logs:          ## tail logs for the whole stack (Ctrl-C to stop)
	$(DC_FULL) logs -f --tail=100

urls:          ## print every service's URL + credentials (ports from .env)
	@echo ""
	@echo "  ========================================================================"
	@echo "   Anime Recommender - service directory   (open the http:// links below)"
	@echo "  ========================================================================"
	@echo ""
	@echo "  [ OPEN IN BROWSER ]"
	@echo "    Web app             http://localhost:$(WEB_PORT)"
	@echo "    API docs (Swagger)  http://localhost:$(API_PORT)/docs"
	@echo "    API health          http://localhost:$(API_PORT)/health"
	@echo "    Langfuse (traces)   http://localhost:$(LANGFUSE_WEB_PORT)"
	@echo "        login:          $(LANGFUSE_INIT_USER_EMAIL) / $(LANGFUSE_INIT_USER_PASSWORD)"
	@echo "    Grafana (metrics)   http://localhost:$(GRAFANA_PORT)"
	@echo "        login:          $(GRAFANA_ADMIN_USER) / $(GRAFANA_ADMIN_PASSWORD)"
	@echo "    RedisInsight        http://localhost:$(REDISINSIGHT_PORT)   (both Redis pre-added)"
	@echo "    Prometheus          http://localhost:$(PROMETHEUS_PORT)   (Status > Targets)"
	@echo "    MinIO console       http://localhost:$(MINIO_CONSOLE_PORT)"
	@echo "        login:          $(MINIO_ROOT_USER) / $(MINIO_ROOT_PASSWORD)"
	@echo ""
	@echo "  [ DATA TIER ]  (client tools - no web UI)"
	@echo "    Postgres (app)      localhost:$(POSTGRES_PORT)   db=anime   (psql / pgAdmin / DBeaver)"
	@echo "    Redis (app cache)   localhost:$(REDIS_PORT)   no password   (or RedisInsight above)"
	@echo "    LocalStack SQS/S3   http://localhost:$(LOCALSTACK_PORT)/_localstack/health"
	@echo "        list queues:    aws --endpoint-url=http://localhost:$(LOCALSTACK_PORT) sqs list-queues"
	@echo ""
	@echo "  [ OBSERVABILITY TIER ]  (make obs)"
	@echo "    OTel Collector      localhost:$(OTEL_GRPC_PORT) gRPC | http://localhost:$(OTEL_HTTP_PORT) HTTP"
	@echo "        metrics export  http://localhost:$(OTEL_PROM_PORT)/metrics   (Prometheus scrapes this)"
	@echo "    ClickHouse          http://localhost:$(CLICKHOUSE_HTTP_PORT)   (native: localhost:$(CLICKHOUSE_NATIVE_PORT))"
	@echo "    Langfuse Postgres   localhost:$(LANGFUSE_POSTGRES_PORT)   db=langfuse"
	@echo "    Langfuse Redis      localhost:$(LANGFUSE_REDIS_PORT)   password=$(LANGFUSE_REDIS_AUTH)"
	@echo "    MinIO S3 API        http://localhost:$(MINIO_API_PORT)   (console is above)"
	@echo ""
	@echo "  Metrics flow: app -> OTel collector -> Prometheus -> Grafana (all local)."
	@echo "  ========================================================================"
	@echo ""

# ╔══════════════════════════════════════════════╗
# ║  Database targets                            ║
# ╚══════════════════════════════════════════════╝
db-up:
	$(DC_DATA) up -d postgres
	@echo "Waiting for postgres to be ready..."
	@until $(DC_DATA) exec -T postgres sh -c 'pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB' >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres ready on localhost:$(POSTGRES_PORT) (credentials: POSTGRES_* in .env)."

db-migrate:
	uv run alembic upgrade head

db-down:
	$(DC_DATA) stop postgres

db-shell:
	$(DC_DATA) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

# ╔══════════════════════════════════════════════╗
# ║  Domain targets                              ║
# ╚══════════════════════════════════════════════╝
ingest:
	uv run python -m anime_ingestion.cli --csv data/anime_with_synopsis.csv

retrieve:
	@test -n "$(QUERY)" || (echo "Usage: make retrieve QUERY='light hearted school anime'" && exit 1)
	uv run python -m anime_retrieval.cli --query "$(QUERY)"

eval:
	uv run python -m anime_eval.cli $(EVAL_ARGS)

# The quality gate CI runs: eval, then compare against evals/baseline.json.
# anime_eval.compare enforces BOTH no-regression-vs-baseline AND lift-over-naive.
eval-gate:
	uv run python -m anime_eval.cli --json $(EVAL_CANDIDATE)
	uv run python -m anime_eval.compare --baseline $(EVAL_BASELINE) --candidate $(EVAL_CANDIDATE)

# Refusal gate: does the model DECLINE what it can't answer, and still ANSWER what it
# can? Costs one LLM call per query, so it's separate from `make eval`. Before the
# refusal path existed, "what is the capital of France" returned three anime.
eval-refusal:
	uv run python -m anime_eval.refusal_cli

# Project LLM_PRICING into Langfuse's model table. Langfuse computes trace cost
# from ITS OWN table, so a model it doesn't know shows $0.00 in the UI while the
# provider still bills. Re-run after any price change (idempotent).
lf-models:
	uv run python scripts/langfuse_models.py

# Mint a short-lived Clerk JWT for smoke/chaos probes (auth fails closed — there
# is no bypass, so verification needs a real signed token).
token:
	@uv run python scripts/dev_token.py

recommend:
	uv run python -m anime_retrieval.recommend_cli --query "$(QUERY)" $(RECOMMEND_ARGS)

# API_PORT/WEB_PORT come from the port block at the top (1005/1006 — keep in
# sync with .env). Override per-invocation: make dev-api API_PORT=9000
dev-api:
	uv run uvicorn anime_api.main:app --reload --port $(API_PORT)

dev-web:
	pnpm --dir apps/web dev -p $(WEB_PORT)

web-build:
	pnpm --dir apps/web build

web-test:
	pnpm --dir apps/web test

web-check:
	pnpm --dir apps/web typecheck && pnpm --dir apps/web lint && pnpm --dir apps/web test

# `dev` = backwards-compat alias for `app` (data + app tier, containerised).
# For hot-reload host dev, use `make db` then `make dev-api` / `make dev-web`.
dev: app

# ╔══════════════════════════════════════════════╗
# ║  Observability targets                       ║
# ╚══════════════════════════════════════════════╝
# The obs tier now lives in its OWN compose file (infra/compose/docker-
# compose.obs.yml) instead of a `--profile obs`. `make obs` is the primary
# target; these obs-up/down/logs aliases are kept for backwards-compat.
obs-up: obs

obs-down:
	$(DC_OBS) down

obs-logs:
	$(DC_OBS) logs -f langfuse-web langfuse-worker

# ╔══════════════════════════════════════════════╗
# ║  Worker targets                              ║
# ╚══════════════════════════════════════════════╝
WORKER_QUEUE ?= feedback
# load_dotenv() first: anime_core.sqs reads os.environ directly (by design —
# containers get env injected), so the host-run path must load .env itself,
# same as the api/worker entrypoints do.
sqs-init:
	uv run python -c "from dotenv import load_dotenv; load_dotenv(); import asyncio; from anime_core.sqs import ensure_queues; print(asyncio.run(ensure_queues()))"

worker:
	uv run python -m anime_worker --queue $(WORKER_QUEUE)

# ╔══════════════════════════════════════════════╗
# ║  Eval gate                                   ║
# ╚══════════════════════════════════════════════╝
# Compare a candidate eval report against the committed baseline. Used both
# locally (debugging) and by the eval-gate CI workflow. Exits 1 on regression,
# 0 on pass, 2 on usage error.
EVAL_BASELINE   ?= evals/baseline.json
EVAL_CANDIDATE  ?= eval_report.json
EVAL_THRESHOLD  ?= 0.03
EVAL_FLOOR      ?= 0.01
EVAL_FORMAT     ?= text

eval-compare:
	@test -f $(EVAL_CANDIDATE) || (echo "Candidate not found: $(EVAL_CANDIDATE) — run 'make eval' first." && exit 1)
	uv run python -m anime_eval.compare \
		--baseline $(EVAL_BASELINE) \
		--candidate $(EVAL_CANDIDATE) \
		--threshold $(EVAL_THRESHOLD) \
		--floor $(EVAL_FLOOR) \
		--format $(EVAL_FORMAT)

# Promote the candidate's advanced metrics into the baseline. Run after an
# intentional metric shift; commit the diff as part of the same PR. See
# docs/repo-setup.md §6.
eval-promote:
	uv run python scripts/eval_promote.py --from $(EVAL_CANDIDATE) --to $(EVAL_BASELINE)

# ╔══════════════════════════════════════════════╗
# ║  Load testing (NFR validation)               ║
# ╚══════════════════════════════════════════════╝
# All k6 targets require BASE_URL + K6_AUTH_TOKEN env vars. See
# tests/load/README.md for installation, auth-token minting, and stack
# bring-up. load-validate works without k6 installed (JS syntax check only).
LOAD_BASE_URL    ?= http://localhost:$(API_PORT)
LOAD_K6_BIN      ?= k6
LOAD_K6_SSE_BIN  ?= ./k6-sse
LOAD_REPORTS_DIR ?= tests/load/reports
LOAD_TS          := $(shell date +%s)

load-validate:
	@for f in tests/load/k6/lib/*.js tests/load/k6/*.js; do \
		node --check "$$f" && echo "  OK    $$f"; \
	done

load-smoke:
	@test -n "$$K6_AUTH_TOKEN" || (echo "K6_AUTH_TOKEN not set — see tests/load/README.md §2" && exit 1)
	$(LOAD_K6_BIN) run -e BASE_URL=$(LOAD_BASE_URL) tests/load/k6/smoke.js

load-baseline:
	@test -n "$$K6_AUTH_TOKEN" || (echo "K6_AUTH_TOKEN not set" && exit 1)
	@mkdir -p $(LOAD_REPORTS_DIR)
	$(LOAD_K6_BIN) run -e BASE_URL=$(LOAD_BASE_URL) \
		--summary-export=$(LOAD_REPORTS_DIR)/sustained_50rps_$(LOAD_TS).json \
		tests/load/k6/sustained_50rps.js

load-peak:
	@test -n "$$K6_AUTH_TOKEN" || (echo "K6_AUTH_TOKEN not set" && exit 1)
	@mkdir -p $(LOAD_REPORTS_DIR)
	$(LOAD_K6_BIN) run -e BASE_URL=$(LOAD_BASE_URL) \
		--summary-export=$(LOAD_REPORTS_DIR)/peak_200rps_$(LOAD_TS).json \
		tests/load/k6/peak_200rps.js

load-ramp:
	@test -n "$$K6_AUTH_TOKEN" || (echo "K6_AUTH_TOKEN not set" && exit 1)
	@mkdir -p $(LOAD_REPORTS_DIR)
	$(LOAD_K6_BIN) run -e BASE_URL=$(LOAD_BASE_URL) \
		--summary-export=$(LOAD_REPORTS_DIR)/ramp_$(LOAD_TS).json \
		tests/load/k6/ramp_to_knee.js

# Streaming scenario needs the xk6-sse-built binary — see tests/load/README.md §5.
load-stream:
	@test -n "$$K6_AUTH_TOKEN" || (echo "K6_AUTH_TOKEN not set" && exit 1)
	@test -x $(LOAD_K6_SSE_BIN) || (echo "Custom k6 binary not found at $(LOAD_K6_SSE_BIN) — build with: docker build -t k6-sse tests/load/k6/xk6 && docker run --rm -i --network host k6-sse run -e BASE_URL=$(LOAD_BASE_URL) -e K6_AUTH_TOKEN=\$$K6_AUTH_TOKEN -v $$(pwd)/tests/load:/load /load/k6/stream_sustained_30rps.js" && exit 1)
	@mkdir -p $(LOAD_REPORTS_DIR)
	$(LOAD_K6_SSE_BIN) run -e BASE_URL=$(LOAD_BASE_URL) \
		--summary-export=$(LOAD_REPORTS_DIR)/stream_$(LOAD_TS).json \
		tests/load/k6/stream_sustained_30rps.js

# ╔══════════════════════════════════════════════╗
# ║  Audits (supply-chain)                       ║
# ╚══════════════════════════════════════════════╝
# Each target wraps a single audit script. Exit codes are stable so future
# CI can gate on them.
audit-secrets:
	uv run python scripts/audit/secrets.py

audit-deps:
	uv run python scripts/audit/deps.py

audit-licenses:
	uv run python scripts/audit/licenses.py

# Sequential — earlier audits often unlock the next (secrets clean before
# deps; deps clean before licenses), so `set -e` semantics here are intentional.
audit-all:
	@$(MAKE) audit-secrets && $(MAKE) audit-deps && $(MAKE) audit-licenses

# ╔══════════════════════════════════════════════╗
# ║  Chaos drills                                ║
# ╚══════════════════════════════════════════════╝
# Each script is paired with chaos-restore for cleanup. Restore is idempotent
# and safe to run any time. ALL chaos scripts require the stack up (`make app`).
chaos-llm:
	bash scripts/chaos/kill_llm.sh

chaos-pg:
	bash scripts/chaos/kill_pg.sh

chaos-net:
	bash scripts/chaos/net_partition.sh

chaos-restore:
	bash scripts/chaos/restore.sh

# ╔══════════════════════════════════════════════╗
# ║  Backup drills                               ║
# ╚══════════════════════════════════════════════╝
backup-dump:
	bash scripts/backup/dump_local.sh

# Usage: make backup-restore DUMP=backups/anime_<ts>.sql.gz
backup-restore:
	@test -n "$(DUMP)" || (echo "Usage: make backup-restore DUMP=backups/anime_<ts>.sql.gz" && exit 1)
	bash scripts/backup/restore_local.sh "$(DUMP)"

backup-drill:
	bash scripts/backup/drill.sh

# ╔══════════════════════════════════════════════╗
# ║  RTBF / GDPR Art 17                          ║
# ╚══════════════════════════════════════════════╝
# Operator CLI wrapper. Default is dry-run; pass DRY=0 to actually delete.
# See docs/hardening/rtbf-procedure.md for the full procedure.
DRY ?= 1
rtbf:
	@test -n "$(USER)" || (echo "Usage: make rtbf USER=user_xxxxxxxx [DRY=0]" && exit 1)
	@if [ "$(DRY)" = "0" ]; then \
	    uv run python scripts/rtbf.py --user "$(USER)" --confirm $(if $(REASON),--reason "$(REASON)",) ; \
	else \
	    uv run python scripts/rtbf.py --user "$(USER)" $(if $(REASON),--reason "$(REASON)",) ; \
	fi

# ╔══════════════════════════════════════════════╗
# ║  Local Docker deploy                         ║
# ╚══════════════════════════════════════════════╝
# Procedure + gate criteria in docs/deploy/stage1-local-docker.md.
deploy-stage1-smoke:
	bash scripts/deploy/smoke_local.sh

# Full Stage 1 acceptance: cold start → migrate + ingest → smoke → drill.
# This is the canonical "Stage 1 passed" sequence; takes ~3-5 min total.
# Run before promoting to Stage 2 OR after any Step-13 docker-compose change.
deploy-stage1:
	@echo "─── Stage 1: cold start ────────────────────────────────────────"
	docker compose down -v
	docker compose up -d
	@echo "Waiting up to 60s for services to report healthy…"
	@for i in $$(seq 1 30); do \
	    if docker compose ps --status running | grep -q api; then break; fi; sleep 2; \
	done
	@sleep 5
	@echo "─── Stage 1: migrate + ingest ──────────────────────────────────"
	$(MAKE) db-migrate
	$(MAKE) ingest
	@echo "─── Stage 1: bash smoke ────────────────────────────────────────"
	$(MAKE) deploy-stage1-smoke
	@echo "─── Stage 1: backup drill ──────────────────────────────────────"
	$(MAKE) backup-drill
	@echo
	@echo "Stage 1 acceptance complete. See docs/deploy/stage1-local-docker.md §4"
	@echo "for the gate-criteria checklist; sign off by adding a row to §7."
