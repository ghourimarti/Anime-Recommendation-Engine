# Run From Scratch — Startup Sequence

How to bring the whole application up from zero, in the exact order the
components must start. Every command is a `make` target (see `Makefile`);
every port and credential is a variable in `.env`.

---

## 0. The port map (memorize this once)

Host ports are numbered **1002–1015 in component startup order** — the number
tells you *when* the component starts. Container-internal ports on the Docker
network stay standard (`postgres:5432`, `api:8000`,...), so only the
`localhost:` side ever changes. All of these are set in the `PORTS` section of
`.env`; change them there and everything follows.

| Order | Port | Component | Why this position |
|---|---|---|---|
| 1 | **1002** | Postgres + pgvector | Data store — everything depends on it |
| 2 | **1003** | Redis | Cache — API needs it at boot |
| 3 | **1004** | LocalStack (SQS/S3) | Queues must exist before API/worker |
| 4 | **1005** | FastAPI backend | Starts after migrate + sqs-init complete |
| 5 | **1006** | Next.js frontend | Last — proxies to the API |
| 6 | **1007** | ClickHouse HTTP | ─┐ |
| 7 | **1008** | ClickHouse native | │ |
| 8 | **1009** | Langfuse Postgres | │ observability stack |
| 9 | **1010** | Langfuse Redis | │ (`--profile obs`, optional) |
| 10 | **1011** | MinIO S3 API | │ |
| 11 | **1012** | MinIO console | │ |
| 12 | **1013** | **Langfuse UI** | │ ← open this one in a browser |
| 13 | **1014** | OTel Collector gRPC | │ app exports spans here |
| 14 | **1015** | OTel Collector HTTP | ─┘ curl debugging |

Port 1001 is skipped — the Windows kernel holds it permanently on this machine.

Two hidden one-shot containers run between 3 and 4: **`migrate`** (alembic →
head) and **`sqs-init`** (create queues + DLQs). `docker compose up` sequences
all of this automatically via `depends_on`; the order above is what you follow
when starting components *manually*.

---

## The stack is split into three tiers (three compose files)

`infra/compose/` holds three files, each a tier; the Makefile composes them:

| `make` target | Tier(s) | Services |
|---|---|---|
| `make db` | data | postgres, redis, localstack |
| `make app` | data + app | + migrate, sqs-init, api, web, worker |
| `make obs` | observability | otel-collector, langfuse (web/worker/pg/redis/clickhouse/minio) |
| `make up` | **everything** | all 16 services (db + app + obs) |
| `make down` | — | stop + remove containers (**keeps** volumes) |
| `make downv` | — | down + **wipe** volumes (destroys corpus/traces) |
| `make upv` | **everything, from scratch** | downv → up → migrate → ingest |
| `make ps` / `logs` / `urls` | — | status / tail logs / print all URLs |

All three files share `name: anime-recommender` → one Docker project + network,
so the api container reaches langfuse/otel by DNS when obs is up, and drops
telemetry silently when obs is down. Tiers stack cleanly: `app` includes `db`,
`up` includes everything.

---

## TL;DR — one command from scratch

```bash
cp .env.example .env        # fill OPENAI_API_KEY, GROQ_API_KEY, CLERK_* (once)
make upv                    # wipe → build all volumes+containers → migrate → ingest
```

`make upv` leaves a fully working, queryable app (web on:1006). It re-ingests
the corpus each time (~$0.01 OpenAI), so use it for a clean-slate rebuild; for
day-to-day starts use `make up` (keeps the existing corpus volume).

---

## 1. One-time machine setup (first clone only)

```bash
# Prerequisites: Docker Desktop (running), uv, Node 20+, pnpm, GNU make.

cp .env.example .env        # then fill in: OPENAI_API_KEY, GROQ_API_KEY,
                            # CLERK_* keys, LANGFUSE_* keys (after step 4).
                            # Ports + local credentials are already set.

uv sync                     # Python workspace (apps/* + packages/*, editable)
pnpm --dir apps/web install # frontend deps
```

## 2. Start the data layer (before anything else)

```bash
make db                     # data tier: postgres(1002) + redis(1003) + localstack(1004)
make db-migrate             # alembic upgrade head (schema before ingest/API)
make ingest                 # one-time corpus load — embeds via OpenAI, ~$0.01
                            #   (skip if the pgdata volume already has the corpus)
```

Verify: `make db-shell` → `SELECT count(*) FROM anime;` → ~268 rows.

> `make db-up` still exists (starts only postgres, waits for healthy) for the
> backup/chaos drills that need just the DB. `make db` starts the whole data tier.

## 3. Start the application

**Route A — everything in Docker (closest to prod):**

```bash
make app                    # data + app tier, in order:
                            #   postgres(1002) → redis(1003) → localstack(1004)
                            #   → migrate + sqs-init (one-shot)
                            #   → api(1005) → web(1006) → worker
                            # (make dev is a backwards-compat alias for this)
```

**Route B — hot-reload development (infra in Docker, app on host):**

```bash
make db                     # infra tier: 1002/1003/1004
make sqs-init               # create SQS queues in LocalStack (one-shot)
make dev-api                # Terminal 1 → FastAPI on localhost:1005 (--reload)
make dev-web                # Terminal 2 → Next.js on localhost:1006
make worker                 # Terminal 3 (optional) → feedback-queue consumer
```

Verify the stack, in dependency order:

```bash
curl -s http://localhost:1004/_localstack/health   # localstack: services "available"
curl -s http://localhost:1005/health               # api liveness: 200
curl -s http://localhost:1005/ready                # api readiness: DB+deps OK
# then open http://localhost:1006 → sign in with the Clerk dev tenant → query
```

## 4. Start observability (optional, heavier — its own tier)

```bash
make obs                    # clickhouse(1007/1008), langfuse-pg(1009),
                            # langfuse-redis(1010), minio(1011/1012),
                            # langfuse UI(1013), otel-collector(1014/1015)
                            # (make obs-up is a backwards-compat alias)
```

First run only: open http://localhost:1013 → sign up → create org/project →
copy the `pk-lf-...`/`sk-lf-...` keys into `.env` (`LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and regenerate `LANGFUSE_BASIC_AUTH` — recipe is in the
`.env` comment). Set `OTEL_SDK_DISABLED=false`, then restart the app tier
(`make app`) so spans flow: API → OTel collector (1014) → Langfuse (1013).

Because obs is a separate tier on the shared network, `make obs` and `make app`
are independent — start/stop either without touching the other.

## 5. Stop / reset

```bash
make down                            # stop + remove ALL containers (volumes SURVIVE)
make obs-down                        # stop ONLY the observability tier
make downv                           # ⚠ down + WIPE volumes — corpus, Langfuse org,
                                     #   traces gone. Requires re-ingest (costs $) and
                                     #   Langfuse re-signup. Full reset.
make upv                             # ⚠ downv + rebuild everything from scratch +
                                     #   migrate + ingest (the clean-slate button)
make deploy-stage1                   # full cold-start acceptance test (down -v →
                                     #   up → migrate → ingest → smoke → backup drill)
```

---

## Changing ports or credentials

1. Edit the `PORTS` / `CREDENTIALS` sections in `.env`.
2. If you changed **Postgres** creds/port: update `DATABASE_URL` in `.env` to
 match (host processes read the URL literally, they don't compose it).
3. If you changed **Redis** port: update `REDIS_URL` the same way.
4. If you changed **API/web** ports: update `API_BASE_URL`, `CORS_ORIGINS`,
 `NEXT_PUBLIC_SITE_URL`, and the matching `?=` defaults at the top of the
 `Makefile` (make cannot read `.env` — the defaults are mirrored there).
5. If you changed **Langfuse UI / OTel** ports: update `LANGFUSE_HOST`,
 `LANGFUSE_BASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`.
6. `docker compose up -d` again — compose re-reads `.env` on every invocation.

**Linux caveat:** ports 1002–1015 are below 1024, which Linux treats as
privileged for *host-run* processes (`make dev-api`, `make dev-web`). Docker
and Windows are unaffected. On a Linux dev box, bump the block to 11002–11015.

## Troubleshooting

| Symptom | Cause → fix |
|---|---|
| `port is already allocated` on `docker compose up` | Another process on a 100x port → `netstat -ano \| findstr:100` then change the port in `.env` |
| API 503 on `/ready` | Postgres not up/migrated → `make db-up && make db-migrate` |
| API 503 on every authed route | `CLERK_JWKS_URL` empty (auth fails closed by design) → set it in `.env` |
| Web can't reach API | `API_BASE_URL` doesn't match `API_PORT` → fix `.env`; CORS error → add the web origin to `CORS_ORIGINS` |
| Worker idle, feedback never lands | Queues missing → `make sqs-init`; LocalStack down → check port 1004 |
| No traces in Langfuse | `OTEL_SDK_DISABLED=true`, or `LANGFUSE_BASIC_AUTH` stale after key rotation → regenerate |
| `make test` import errors | Workspace not synced → `uv sync` |
