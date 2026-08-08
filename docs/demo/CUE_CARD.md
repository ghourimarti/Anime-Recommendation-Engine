# 🎬 CUE CARD — Anime Recommender demo (keep beside you while recording)

**One-page glance card.** Click paths + narration beats only — no explanations.
Full script: [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) · Detailed narration: [DEMO_RUNBOOK_EXPANDED_SCENES.md](DEMO_RUNBOOK_EXPANDED_SCENES.md)

---

## ⏱ PRE-FLIGHT (before you hit record)
- [ ] Day-before: `.env` → `OTEL_SDK_DISABLED=false` · `make upv` · `make lf-models` · `make app`
- [ ] Now: `make up` → `make urls` (keep visible) → `make ps` (all Up/healthy)
- [ ] `make token` → copy JWT (KEEP OFF-SCREEN)
- [ ] 2 warm-up queries done · repeat query is faster (cache) · Langfuse shows a trace
- [ ] Browser zoom 110–125% · cursor highlight ON · hide `.env`/JWT/Clerk · tabs in order

**Tabs L→R:** Web `1006` · Swagger `1005/docs` · Langfuse `1013` · Prom `1018` · Grafana `1019` · RedisInsight `1016` · MinIO `1012` · Terminal

**Logins:** Langfuse `admin@anime.local / anime-admin-1234` · Grafana `admin/admin` · MinIO `minio/miniosecret`

**⚠ NEVER live:** `make downv` / `make upv` (wipes data) · always `make chaos-restore` after any `chaos-*` · `make rtbf` keep default DRY

---

## S0 — HOOK (0:30)  ·  [Web `:1006` landing]
- Beat: "AI recommender — plain English → grounded, cited answers in ~1s."
- Beat: "The answer is the easy 10%. I'll show you the product **around** it — observable, cost-controlled, self-healing."
- 👁 *This is a product, not a prototype.*

## S1 — SYSTEM UP (1:25)  ·  [Terminal → Prom Targets]
- `make ps` → point at **(healthy)**; migrate + sqs-init = Exited(0) (on purpose)
- `:1018/targets` → all **UP**
- Beat: "16 containers, one command. Every service **health-checked** → self-healing, no start-up race."
- Beat: "migrate + queues ran **before** the app was allowed up."
- Beat: "Green targets = it's watching itself before I've sent a request."
- 👁 *(healthy) column + all-green Targets.*

## S2 — FRONTEND QUERY (1:20)  ·  [Web `:1006`]
- Type: *"light-hearted school anime with a strong female lead"* → submit → tokens stream → cards + source chips → thumbs-up one
- Beat: "Streams token-by-token → feels fast, no bounce."
- Beat: "Each rec shows its **source** = grounded = can't hallucinate."
- Beat: "Thumbs-up → background queue, never blocks the user."
- 👁 *Streaming + source chips.*

## S3 — GOLDEN THREAD ⭐ (3:00)  ·  same query, 8 tools
1. **Swagger** `:1005/docs` → `POST /v1/recommend` → Authorize (JWT) → Try it out → `{"query":"a slow-burn psychological thriller under 24 episodes"}` → Execute → show 200 + `query_history_id`
   - "Same question, straight to the API. One request → footprint everywhere. Let's follow it."
2. **Logs** `docker compose logs --tail=20 api` → point `request_id` / `trace_id`
   - "Structured JSON. PII redacted. This trace ID is the thread."
3. **Langfuse** `:1013` → Tracing → newest trace → expand
   - "Retrieval + docs + **real prompt** + model + tokens + **cost/request** + per-step latency."
4. **Prometheus** `:1018` → Graph → `sum(rate(anime_http_requests_total{service_name="anime-api"}[5m]))`
   - "Same request moved a metric. 'Scrape' = pull a snapshot every 15s → chart + alert."
5. **Grafana** `:1019` → **API Overview** → Request rate + p95
   - "Raw data → one-glance health."
6. **RedisInsight** `:1016` → `app-cache` → keys `resp:*` / `sem:*`
   - "Cached. Same/similar question → no LLM call, ms, ~$0."
7. **Postgres** `make db-shell` →
   `SELECT id,query,created_at FROM query_history ORDER BY created_at DESC LIMIT 1;`
   `SELECT * FROM usage_daily ORDER BY updated_at DESC LIMIT 1;`
   - "History row (user can revisit) + usage row (tokens + $ per user/day) → no surprise bill."
8. **MinIO** `:1012` → bucket `langfuse`
   - "Raw trace events in durable object storage."
- 👁 *Same request in 8 places = ONE connected system.*

## S4 — OBSERVABILITY DEEP-DIVE (2:30, optional in tight cut)
**S4a Langfuse** `:1013` trace → "What did it do? (prompt+context) · What cost? ($/req) · Was it fast? (per-step). Bad answer → open trace → fixed in <1 min."
**S4b Prometheus** `:1018` → **Status ▸ Targets** (all UP), then:
- `sum by (status_class) (rate(anime_http_requests_total{service_name="anime-api"}[5m]))`
- `histogram_quantile(0.95, sum(rate(anime_http_duration_seconds_bucket{service_name="anime-api",route="/v1/recommend"}[5m])) by (le))`
- `sum(increase(anime_llm_cost_usd_total{service_name="anime-api"}[1h]))`
- "Source of truth. Green targets = nothing unmonitored. Ask it anything."
**S4c Grafana** `:1019` **API Overview** → "3-a.m. view. Traffic/errors/latency = is it up. Spend + cost/model = money before finance sees it. **Unpriced calls = must be 0**. Triage in 10s."
- 👁 *Targets all UP · p95 + spend on one screen.*

## S5 — DATA LAYER (1:15)
- **RedisInsight** `:1016` `app-cache` → keys `resp:*`/`sem:*`/`embed:*` → **re-run a query on web → faster (cache hit)**
- **Postgres** `make db-shell` → `\dt` (6 tables) → query_history + usage_daily rows
- **MinIO** `:1012` → bucket `langfuse`
- Beat: "3 caches (exact/semantic/embedding) → repeat = free + instant."
- Beat: "Every row tied to a user → GDPR delete = one clean op."
- 👁 *Repeat query gets faster, LIVE.*

## S6 — DURABILITY ⭐ (1:45)  ·  two failures, both correct
**S6a AI outage / kill-switch:** `make chaos-llm`
- Expect: **HTTP 200 + `degraded=true` + non-empty popular list**
- Langfuse this window: **0 LLM calls, $0**
- Beat: "Provider dies / cost kill-switch → usable answer, not an error. 503 would be a FAIL. Degrade, don't fail."
- ▶ `make chaos-restore`
**S6b DB outage:** `make chaos-pg`
- Expect: `/health` **200** · `/ready` **503** · `/v1/recommend` friendly 503
- Beat: "Liveness green (don't restart) · readiness red (LB pulls traffic) · auto-rejoins on restore. Data on disk untouched."
- ▶ `make chaos-restore` → `/ready` 200
- 👁 *`/health` 200 while `/ready` 503 at the same moment.*

## S7 — CLOSE (0:45)  ·  [Grafana API Overview full]
- Beat: "Streaming + cited · traceable end-to-end · cost to the cent + kill-switch · survives provider + DB outage · self-healing."
- Beat: "Not a one-time trick — production-ready. Same containers run on K8s w/ autoscaling + canary zero-downtime deploys."
- Beat: "Happy to go deeper on any layer."
- 👁 *End on the LIVE dashboard, not a slide.*

---
**EDIT ORDER:** shoot S3 + S6 first (money scenes) → then S0/S1/S2/S7 → then S4/S5.
**MAIN CUT (8–12m):** S0·S1·S2·S3·S6·S7  ·  **DEEP-DIVE (20–30m):** insert S4·S5 between S3 and S6.
**Before publishing:** scrub every frame for `.env` / raw JWT / Clerk dashboard.
