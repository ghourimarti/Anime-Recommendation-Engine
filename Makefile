.PHONY: help sync test lint format typecheck check clean
.PHONY: up up-vllm up-sglang down downv upv llm-status ps logs urls service_ls
.PHONY: up-data up-app up-obs down-data down-app down-obs downv-data downv-obs net-down wait-api ps-stack logs-obs
.PHONY: ingest retrieve eval eval-gate eval-refusal recommend dev-api dev-web web-build web-test web-check lf-models token
.PHONY: db-up db-migrate db-down db-shell worker sqs-init
.PHONY: venue-status venue-up-vllm venue-up-sglang venue-down-vllm venue-down-sglang venue-down venue-bench venue-compare
.PHONY: base-images-refresh base-images-check render-verify package
.PHONY: eval-compare eval-promote
.PHONY: load-validate load-smoke load-baseline load-peak load-ramp load-stream
.PHONY: audit-secrets audit-deps audit-licenses audit-all
.PHONY: chaos-llm chaos-pg chaos-net chaos-restore
.PHONY: backup-dump backup-restore backup-drill
.PHONY: rtbf
.PHONY: deploy-stage1-smoke deploy-stage1

# ╔══════════════════════════════════════════════╗
# ║  Local stack — how the commands are built    ║
# ╚══════════════════════════════════════════════╝
# BASE targets are the only ones that call docker compose. One tier each:
#   up-data      postgres + redis + localstack + redisinsight   (waits until healthy)
#   up-app       sqs-init + migrate + api + web + worker        (depends on up-data)
#   up-obs       otel + prometheus + grafana + langfuse stack   (independent)
#   down-<tier>  stop + remove that tier      downv-<tier>  ...and delete its volumes
#   venue-up-vllm / venue-up-sglang           GPU venue; each stops the other first
#
# Every other command is BUILT from base targets, so it reads as its own steps:
#   up          venue-down        + data + app + obs                    LLM: Groq / OpenAI
#   up-vllm     venue-down-sglang + data + app + obs + venue-up-vllm    LLM: vLLM on the GPU
#   up-sglang   venue-down-vllm   + data + app + obs + venue-up-sglang  LLM: SGLang on the GPU
#   down        venue + obs + app + data + network                      (KEEPS volumes)
#   downv       same, deleting volumes       (DESTRUCTIVE — never the model-weight cache)
#   upv         downv + up + migrate + ingest (from scratch)
#
# Three rules the structure depends on:
#  1. up-vllm does NOT reuse `up`. `up` pins VENUE_ROUTING=false, and make applies
#     a prerequisite's own setting over its caller's — up-vllm would silently run
#     API-only. (Checked with a scratch Makefile on GNU Make 4.4.1.)
#  2. The venue starts AFTER the tiers. It joins the compose network, which exists
#     only once compose has created it; started first, it lands on the default
#     bridge and the containerised api silently falls back to the hosted LLM.
#  3. `down` takes the venue down first. A container still attached to the network
#     makes compose exit 0 yet leave the network behind ("Resource is still in use").
#
# Prerequisites run once each, left to right; .NOTPARALLEL keeps that under -j.
.NOTPARALLEL:

# All three compose files declare `name: anime-recommender`: one project, one
# network, so the api reaches langfuse-web / otel-collector (and the venue) by DNS.
#
# `--env-file .env` is passed EXPLICITLY: with compose files in infra/compose/,
# docker compose does NOT auto-load `.env` from CWD. Skipping it makes the web
# build bake the fallback (empty Clerk key) into the client bundle.
COMPOSE_DIR := infra/compose
COMPOSE     := docker compose --env-file .env
DATA_FILES  := -f $(COMPOSE_DIR)/docker-compose.data.yml
# The app tier's depends_on names data services, so compose must load both files
# to resolve them — only the app services are started or stopped.
APP_FILES   := $(DATA_FILES) -f $(COMPOSE_DIR)/docker-compose.app.yml
OBS_FILES   := -f $(COMPOSE_DIR)/docker-compose.obs.yml
ALL_FILES   := $(APP_FILES) $(OBS_FILES)
COMPOSE_NET := anime-recommender_default

# Each base target loads only its own tier's compose files, so compose reports the
# other tiers' containers as "orphans" on every call. They are not orphans: same
# project, started from the other files. Ignoring them silences the warning and
# means an added `--remove-orphans` can never delete a running tier.
export COMPOSE_IGNORE_ORPHANS := true

DATA_SERVICES := postgres redis localstack redisinsight
APP_SERVICES  := sqs-init migrate api web worker
OBS_SERVICES  := otel-collector prometheus grafana clickhouse langfuse-postgres langfuse-redis \
                 minio minio-create-bucket langfuse-worker langfuse-web

# Which LLM the containerised api uses. The mode targets set it (up / up-vllm /
# up-sglang); a bare `make up-app` is API-only. .env's LLM_VENUE_ROUTING_ENABLED
# only affects a host-run api (make dev-api) — see docker-compose.app.yml.
VENUE_ROUTING ?= false
API_WAIT_SECS ?= 120

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
	@echo "── Run the app - pick the LLM ────────────────────────────────────────"
	@echo "  make up          API-based LLM (Groq / OpenAI) - stops any GPU venue first"
	@echo "  make up-vllm     self-hosted vLLM   - stops SGLang first (~4 min cold model load)"
	@echo "  make up-sglang   self-hosted SGLang - stops vLLM first   (~4 min cold model load)"
	@echo "  make llm-status  which LLM the RUNNING api actually uses"
	@echo "  make upv         FROM SCRATCH: downv -> up -> migrate -> ingest"
	@echo "  make down        venue + obs + app + data + network   (KEEPS volumes)"
	@echo "  make downv       down + WIPE volumes (DESTRUCTIVE; model-weight cache is kept)"
	@echo "  make ps|logs|urls   status incl. venue | tail logs | service URLs (no credentials)"
	@echo "  make service_ls     every service: status, URLs and local credentials (pgAdmin, MinIO, ...)"
	@echo ""
	@echo "── One tier at a time - what the commands above are built from ───────"
	@echo "  make up-data | down-data | downv-data   postgres + redis + localstack + redisinsight"
	@echo "  make up-app  | down-app                 migrate + sqs-init + api + web + worker (starts data)"
	@echo "  make up-obs  | down-obs  | downv-obs    otel + prometheus + grafana + langfuse (~1-3 min cold)"
	@echo "  make logs-obs                           tail Langfuse web + worker logs"
	@echo ""
	@echo "── Local dev (hot reload) ────────────────────────────────────────────"
	@echo "  make dev-api    FastAPI on :$(API_PORT)  (uvicorn --reload; starts the data tier)"
	@echo "  make dev-web    Next.js on :$(WEB_PORT)  (needs an api: make up-app or make dev-api)"
	@echo "  make worker     run an SQS worker    (WORKER_QUEUE=feedback; starts the data tier)"
	@echo "  make sqs-init   create local SQS queues + DLQs in LocalStack"
	@echo ""
	@echo "── Database ──────────────────────────────────────────────────────────"
	@echo "  make db-up      start ONLY postgres (waits for healthy)"
	@echo "  make db-migrate alembic upgrade head"
	@echo "  make db-down    stop the postgres container"
	@echo "  make db-shell   open psql in the running container"
	@echo ""
	@echo "── Workspace ─────────────────────────────────────────────────────────"
	@echo "  make sync       uv sync (resolve workspace + dev deps)"
	@echo "  make test       run all tests"
	@echo "  make lint | format | typecheck"
	@echo "  make check      lint + typecheck + test"
	@echo "  make clean      remove caches"
	@echo ""
	@echo "── Domain (RAG pipeline; each starts the data tier it needs) ─────────"
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
	@echo "  make chaos-llm | chaos-pg | chaos-net | chaos-restore   (chaos-* start the app tier)"
	@echo "  make backup-dump | backup-restore DUMP=path | backup-drill"
	@echo "  make rtbf USER=<clerk-user-id> [DRY=0]   RTBF operator path (default dry-run)"
	@echo "  make deploy-stage1-smoke | deploy-stage1"
	@echo ""
	@echo "── GPU venue (self-hosted LLM; ONE engine at a time - 12 GB card) ────"
	@echo "  make venue-status       GPU free VRAM + running venue containers"
	@echo "  make venue-up-vllm      start vLLM on :$(VLLM_PORT) (stops SGLang first)"
	@echo "  make venue-up-sglang    start SGLang on :$(SGLANG_PORT) (stops vLLM first; memory fraction $(SGLANG_MEM_FRACTION))"
	@echo "                          both: context $(VENUE_CONTEXT_LEN) tokens, wait up to VENUE_WAIT_SECS=$(VENUE_WAIT_SECS)s to load"
	@echo "  make venue-down-vllm | venue-down-sglang | venue-down (both)"
	@echo "  make venue-bench [ENGINE=sglang]   benchmark (starts that engine if needed)"
	@echo "  make venue-compare      head-to-head vLLM vs SGLang (parity-checked)"
	@echo ""
	@echo "── Release packaging (build once, deploy many) ───────────────────────"
	@echo "  make base-images-check    fail if base-images.lock is stale (CI gate)"
	@echo "  make base-images-refresh  re-resolve base tags -> digests; commit alone"
	@echo "  make render-verify        render every vendor x env; validate incl. CRDs"
	@echo "  make package [VERSION=x]  local bundle: 3 images on pinned bases + chart tgz in dist/"

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
# ║  Run the app — built from base targets       ║
# ╚══════════════════════════════════════════════╝
# No docker compose calls in this section: every command is a list of steps.

up: VENUE_ROUTING := false
up: venue-down up-data up-app up-obs wait-api llm-status urls
	@echo "  First run on this machine? make upv also migrates + ingests the corpus."

up-vllm: VENUE_ROUTING := true
up-vllm: venue-down-sglang up-data up-app up-obs venue-up-vllm wait-api llm-status urls

up-sglang: VENUE_ROUTING := true
up-sglang: venue-down-vllm up-data up-app up-obs venue-up-sglang wait-api llm-status urls

down: venue-down down-obs down-app down-data net-down

downv: venue-down downv-obs down-app downv-data net-down

# From scratch: wipe → bring everything up → migrate → ingest. Ingest embeds
# ~268 rows via OpenAI (~$0.01; needs OPENAI_API_KEY).
upv: downv up db-migrate ingest
	@echo "  upv complete - full stack up, schema migrated, corpus ingested."
	@bash scripts/service_ls.sh --urls

ps: ps-stack venue-status

# ╔══════════════════════════════════════════════╗
# ║  Base targets — the only compose calls       ║
# ╚══════════════════════════════════════════════╝
up-data:
	$(COMPOSE) $(DATA_FILES) up -d --wait $(DATA_SERVICES)
	@echo "  data tier up: postgres :$(POSTGRES_PORT) | redis :$(REDIS_PORT) | localstack :$(LOCALSTACK_PORT)"

# VENUE_ROUTING is passed on the command line because the api container also
# reads .env, whose value would otherwise decide for every command.
up-app: up-data
	VENUE_ROUTING=$(VENUE_ROUTING) $(COMPOSE) $(APP_FILES) up --build -d $(APP_SERVICES)
	@echo "  app tier up (venue routing=$(VENUE_ROUTING)): api http://localhost:$(API_PORT) | web http://localhost:$(WEB_PORT)"

up-obs:
	$(COMPOSE) $(OBS_FILES) up -d $(OBS_SERVICES)
	@echo "  observability up - first cold start ~1-3 min (ClickHouse + Langfuse migrations)"
	@echo "  Langfuse http://localhost:$(LANGFUSE_WEB_PORT) | OTel localhost:$(OTEL_GRPC_PORT) gRPC / $(OTEL_HTTP_PORT) HTTP"
	@echo "  Tracing: set OTEL_SDK_DISABLED=false in .env, then make up-app"

down-app:
	$(COMPOSE) $(APP_FILES) down $(APP_SERVICES)

# The data tier cannot go down under a running app.
down-data: down-app
	$(COMPOSE) $(DATA_FILES) down $(DATA_SERVICES)

down-obs:
	$(COMPOSE) $(OBS_FILES) down $(OBS_SERVICES)

# down -v <services> deletes only those services' volumes. The model-weight cache
# (vllm-hf-cache) is created by the venue scripts, not compose, so it is never hit.
downv-data: down-app
	$(COMPOSE) $(DATA_FILES) down -v $(DATA_SERVICES)

downv-obs:
	$(COMPOSE) $(OBS_FILES) down -v $(OBS_SERVICES)

# Per-tier `down` leaves the shared network; remove it once nothing is attached.
net-down:
	@if docker network inspect $(COMPOSE_NET) >/dev/null 2>&1; then \
	    docker network rm $(COMPOSE_NET) >/dev/null && echo "  network $(COMPOSE_NET) removed"; \
	fi

wait-api:
	@printf "  waiting for api /health"; \
	for i in $$(seq 1 $$(( $(API_WAIT_SECS) / 2 ))); do \
	    if curl -sf -o /dev/null http://localhost:$(API_PORT)/health 2>/dev/null; then echo " ok"; exit 0; fi; \
	    printf "."; sleep 2; \
	done; \
	echo; echo "  FAIL  api not healthy after $(API_WAIT_SECS)s — docker logs anime-api --tail 50"; exit 1

# Reads the RUNNING containers, not .env or this file — see the script header.
llm-status:
	@bash scripts/venue/llm_status.sh

ps-stack:
	$(COMPOSE) $(ALL_FILES) ps

logs:
	$(COMPOSE) $(ALL_FILES) logs -f --tail=100

logs-obs:
	$(COMPOSE) $(OBS_FILES) logs -f langfuse-web langfuse-worker

# URLs + live status, NO credentials - printed at the end of every `make up*`.
urls:
	@bash scripts/service_ls.sh --urls

# Every component with live status, URLs and connection details INCLUDING local
# credentials: both Postgres DBs (pgAdmin fields), Redis, ClickHouse, MinIO,
# Langfuse, Grafana, vLLM / SGLang. Values are read from .env at run time.
service_ls:
	@bash scripts/service_ls.sh

# ╔══════════════════════════════════════════════╗
# ║  Database targets                            ║
# ╚══════════════════════════════════════════════╝
db-up:
	$(COMPOSE) $(DATA_FILES) up -d --wait postgres
	@echo "Postgres ready on localhost:$(POSTGRES_PORT) (credentials: POSTGRES_* in .env)."

db-migrate: up-data
	uv run alembic upgrade head

db-down:
	$(COMPOSE) $(DATA_FILES) stop postgres

db-shell: up-data
	$(COMPOSE) $(DATA_FILES) exec postgres sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'

# ╔══════════════════════════════════════════════╗
# ║  Domain targets                              ║
# ╚══════════════════════════════════════════════╝
# Each starts the tier it needs first (a no-op when it is already up). CI does not
# call make — the workflows run uv directly — so this never starts Docker in CI.
ingest: up-data
	uv run python -m anime_ingestion.cli --csv data/anime_with_synopsis.csv

retrieve: up-data
	@test -n "$(QUERY)" || (echo "Usage: make retrieve QUERY='light hearted school anime'" && exit 1)
	uv run python -m anime_retrieval.cli --query "$(QUERY)"

eval: up-data
	uv run python -m anime_eval.cli $(EVAL_ARGS)

# The quality gate CI runs: eval, then compare against evals/baseline.json.
# anime_eval.compare enforces BOTH no-regression-vs-baseline AND lift-over-naive.
eval-gate: up-data
	uv run python -m anime_eval.cli --json $(EVAL_CANDIDATE)
	uv run python -m anime_eval.compare --baseline $(EVAL_BASELINE) --candidate $(EVAL_CANDIDATE)

# Refusal gate: does the model DECLINE what it can't answer, and still ANSWER what it
# can? Costs one LLM call per query, so it's separate from `make eval`. Before the
# refusal path existed, "what is the capital of France" returned three anime.
eval-refusal: up-data
	uv run python -m anime_eval.refusal_cli

# Project LLM_PRICING into Langfuse's model table. Langfuse computes trace cost
# from ITS OWN table, so a model it doesn't know shows $0.00 in the UI while the
# provider still bills. Re-run after any price change (idempotent).
lf-models: up-obs
	uv run python scripts/langfuse_models.py

# Mint a short-lived Clerk JWT for smoke/chaos probes (auth fails closed — there
# is no bypass, so verification needs a real signed token).
token:
	@uv run python scripts/dev_token.py

recommend: up-data
	uv run python -m anime_retrieval.recommend_cli --query "$(QUERY)" $(RECOMMEND_ARGS)

# API_PORT/WEB_PORT come from the port block at the top (1005/1006 — keep in
# sync with .env). Override per-invocation: make dev-api API_PORT=9000
dev-api: up-data
	uv run uvicorn anime_api.main:app --reload --port $(API_PORT)

# No stack prerequisite on purpose: port $(API_PORT) is served EITHER by the
# containerised api (up-app) OR by a host api (dev-api). Auto-starting one would
# collide with the other, so start the api you want first.
dev-web:
	pnpm --dir apps/web dev -p $(WEB_PORT)

web-build:
	pnpm --dir apps/web build

web-test:
	pnpm --dir apps/web test

web-check:
	pnpm --dir apps/web typecheck && pnpm --dir apps/web lint && pnpm --dir apps/web test

# ╔══════════════════════════════════════════════╗
# ║  Worker targets                              ║
# ╚══════════════════════════════════════════════╝
WORKER_QUEUE ?= feedback
# load_dotenv() first: anime_core.sqs reads os.environ directly (by design —
# containers get env injected), so the host-run path must load .env itself,
# same as the api/worker entrypoints do.
sqs-init: up-data
	uv run python -c "from dotenv import load_dotenv; load_dotenv(); import asyncio; from anime_core.sqs import ensure_queues; print(asyncio.run(ensure_queues()))"

worker: up-data
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
# No stack prerequisite, for the same reason as dev-web: the api under test may be
# the container (up-app), a host api (dev-api), or a remote LOAD_BASE_URL.
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
# Each script is paired with chaos-restore for cleanup. chaos-* bring the app tier
# up themselves; chaos-restore has no prerequisite so it still runs against a
# half-broken stack — which is its whole job. Restore is idempotent.
chaos-llm: up-app
	bash scripts/chaos/kill_llm.sh

chaos-pg: up-app
	bash scripts/chaos/kill_pg.sh

chaos-net: up-app
	bash scripts/chaos/net_partition.sh

chaos-restore:
	bash scripts/chaos/restore.sh

# ╔══════════════════════════════════════════════╗
# ║  Backup drills                               ║
# ╚══════════════════════════════════════════════╝
backup-dump: up-data
	bash scripts/backup/dump_local.sh

# Usage: make backup-restore DUMP=backups/anime_<ts>.sql.gz
backup-restore: up-data
	@test -n "$(DUMP)" || (echo "Usage: make backup-restore DUMP=backups/anime_<ts>.sql.gz" && exit 1)
	bash scripts/backup/restore_local.sh "$(DUMP)"

backup-drill: up-data
	bash scripts/backup/drill.sh

# ╔══════════════════════════════════════════════╗
# ║  RTBF / GDPR Art 17                          ║
# ╚══════════════════════════════════════════════╝
# Operator CLI wrapper. Default is dry-run; pass DRY=0 to actually delete.
# See docs/hardening/rtbf-procedure.md for the full procedure.
DRY ?= 1
rtbf: up-data
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
deploy-stage1-smoke: up-app
	bash scripts/deploy/smoke_local.sh

# Full Stage 1 acceptance: cold data tier → app → migrate + ingest → smoke → drill.
# The canonical "Stage 1 passed" sequence; ~3-5 min. API-based LLM, so the gate
# never depends on the GPU. Run before promoting to Stage 2 OR after any compose change.
deploy-stage1: VENUE_ROUTING := false
deploy-stage1: venue-down downv-data up-app wait-api db-migrate ingest deploy-stage1-smoke backup-drill
	@echo
	@echo "Stage 1 acceptance complete. See docs/deploy/stage1-local-docker.md §4"
	@echo "for the gate-criteria checklist; sign off by adding a row to §7."

# ── GPU venue (S19/S20 — self-hosted LLM serving) ─────────────────────────
# The 12 GB card holds exactly ONE 7B model, so vLLM and SGLang are mutually
# exclusive — each venue-up target stops the other engine first. Both are
# measured by the same harness against the same prompt fixture so the engine
# is the only variable. Stopping removes containers only; images and the
# vllm-hf-cache weights volume are never deleted.
# Host ports, one per engine, continuing the 1002-1019 block above. Inside the app
# network both engines listen on 8000 behind the alias anime-venue, so the
# containerised api's URL never changes with the engine; only host-side tools
# (venue-bench, a host-run api via LLM_VENUE_URL in .env) need the right port.
SGLANG_PORT ?= 1020
VLLM_PORT   ?= 1021
ENGINE      ?= vllm
VENUE_PORT_vllm   = $(VLLM_PORT)
VENUE_PORT_sglang = $(SGLANG_PORT)
VENUE_URL  ?= http://localhost:$(VENUE_PORT_$(ENGINE))/v1
VENUE_RUNS ?= 20

venue-status:
	@nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv 2>/dev/null || echo "nvidia-smi unavailable"
	@echo
	@echo "venue containers:"
	@docker ps -a --filter "name=anime-vllm" --filter "name=anime-sglang" \
	    --format "  {{.Names}}  {{.Status}}" 2>/dev/null || true
	@docker ps -a --filter "name=anime-vllm" --filter "name=anime-sglang" -q 2>/dev/null | grep -q . \
	    || echo "  (none)"

# How long a venue script waits for /v1/models before failing. The scripts
# default to 300 s. SGLang cold starts measured on this host: 363 s, 631 s and
# 1,118 s (2026-09-13/14); 900 s failed on the last. 1800 s is
# P5-Medical-Chatbot's ENGINE_WAIT on the same card. The cause of the slow starts
# is still unknown — not VRAM (the 1,118 s start had 4.5 GB free) and not the
# C: drive. Override per run: make up-sglang VENUE_WAIT_SECS=3600
VENUE_WAIT_SECS ?= 1800

# Context window for BOTH engines (vLLM --max-model-len, SGLang --context-length),
# one variable so they cannot drift. It must cover the app's budget:
# LLM_MAX_INPUT_TOKENS 3000 + LLM_MAX_OUTPUT_TOKENS 1200 = 4,200 tokens. At 4096
# SGLang rejected such a request with HTTP 400, and the app silently fell back to
# Groq / OpenAI. The S19/S20 benchmarks ran at 4096.
VENUE_CONTEXT_LEN ?= 8192

# SGLang's --mem-fraction-static is a share of the card's TOTAL VRAM, and it sets
# the KV cache — how many tokens SGLang can hold at once. Measured on this card
# with Qwen2.5-7B-AWQ:
#   0.50 → 1,618-token KV cache; prompts over 1,612 tokens rejected (app allows 3,000)
#   0.55 → 11,881 tokens, 4.87 GB free after the pool (another container)
#   0.90 → 83,721 tokens, 0.37 GB free — almost nothing left for the Windows desktop
# 0.70 sits between: estimated ~42k tokens and ~3 GB free (confirm with
# /get_server_info after a start). P5-Medical-Chatbot's 0.50 did not transfer.
SGLANG_MEM_FRACTION ?= 0.70

venue-up-vllm: venue-down-sglang
	bash scripts/venue/up_vllm.sh --port $(VLLM_PORT) --max-len $(VENUE_CONTEXT_LEN) --wait $(VENUE_WAIT_SECS)

venue-up-sglang: venue-down-vllm
	bash scripts/venue/up_sglang.sh --port $(SGLANG_PORT) --mem-frac $(SGLANG_MEM_FRACTION) --context-len $(VENUE_CONTEXT_LEN) --wait $(VENUE_WAIT_SECS)

venue-down-vllm:
	@bash scripts/venue/down_venue.sh vllm

venue-down-sglang:
	@bash scripts/venue/down_venue.sh sglang

venue-down: venue-down-vllm venue-down-sglang

venue-bench: venue-up-$(ENGINE)
	uv run python scripts/bench_venue.py --engine $(ENGINE) \
	    --url $(VENUE_URL) --runs $(VENUE_RUNS)

venue-compare:
	uv run python scripts/venue/compare.py

# ── Release packaging (P6) ────────────────────────────────────────────────
# base-images.lock is the authoritative pin for what we build ON. A bump is a
# supply-chain event: new upstream packages, new CVEs, a new Trivy result. It
# gets its own command, its own review and its own commit — never a line buried
# in a feature PR.
base-images-check:
	bash scripts/release/refresh_base_images.sh --check

base-images-refresh:
	bash scripts/release/refresh_base_images.sh

# Render every vendor x env and validate against pinned K8s + CRD schemas (P6.9).
# kubeconform checks SCHEMAS, not whether a cluster runs the controller, so the
# script also enforces which CRD kinds each vendor may emit, and runs a negative
# control proving the gate can fail.
render-verify:
	bash scripts/release/render_verify.sh

# Local release bundle (P6.8): the same inputs CI builds from, and nothing pushed,
# scanned or signed (that only happens in .github/workflows/release.yml). Images
# are built on the digest-pinned bases from base-images.lock, the chart is
# render-verified first and packaged with chart version = app version (G4).
VERSION ?= 0.0.0-local
package: render-verify
	@set -a; . ./base-images.lock; set +a; \
	docker build --build-arg UV_IMAGE="$$UV_IMAGE" -f apps/api/Dockerfile -t anime-recommender/api:$(VERSION) . && \
	docker build --build-arg NODE_IMAGE="$$NODE_IMAGE" -f apps/web/Dockerfile -t anime-recommender/web:$(VERSION) apps/web && \
	docker build --build-arg UV_IMAGE="$$UV_IMAGE" -f apps/worker/Dockerfile -t anime-recommender/worker:$(VERSION) .
	@mkdir -p dist
	helm package infra/k8s/helm/anime-recommender --version $(VERSION) --app-version $(VERSION) -d dist
	@echo "  bundle: anime-recommender/{api,web,worker}:$(VERSION) + dist/anime-recommender-$(VERSION).tgz"
