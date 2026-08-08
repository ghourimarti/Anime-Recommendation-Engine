# Demo-Video Runbook — Anime Recommender (production-grade RAG)

> A click-by-click script + runbook for screen-recording a client demo. Everything
> below is grounded in the **real repo** (compose service names, `.env` ports 1002–1019,
> real metric names, the real Grafana dashboard, the real chaos scripts). Where your
> brief assumed something that doesn't match the code, it's **flagged 🔧 CORRECTION**.

---

## 0. Read this first — corrections to your brief (so nothing surprises you on camera)

| Your assumption | Reality in the repo | What to do on camera |
|---|---|---|
| `make up` | ✅ exists — brings up **all 16 services** (db+app+obs). But a *first-ever* run also needs `make db-migrate` + `make ingest`. `make upv` does the whole thing from scratch (wipe → up → migrate → ingest). | Run `make upv` **the day before** (embeds the corpus, ~$0.01 OpenAI). On demo day the stack is warm — just `make up` or leave it running. |
| Grafana shows "cache hit rate" + "queue depth" panels | 🔧 The dashboard **"API Overview"** has: Request rate, Error rate (5xx), p95 /v1/recommend, LLM spend, Unpriced calls, Request rate by route, Responses by status class, Latency p50/p95/p99, Outbound provider latency, LLM cost/hour by model, Tokens/s, **Worker jobs by outcome**, Scrape-up. **No dedicated cache-hit or queue-depth panel.** | Show cache in **RedisInsight** + **Langfuse** (a cached repeat = 0 LLM cost). Show queue health via the **"Worker jobs by outcome"** panel + SQS. Don't promise a cache panel. |
| MinIO = app object storage / query artifacts | 🔧 MinIO is **Langfuse's S3 blob store** (bucket `langfuse`), for trace-event payloads. The app's own S3 is LocalStack (used by workers, **not** written on the query path). | Narrate MinIO as "where Langfuse durably stores the raw trace events" — a real object-store tier in the stack. Don't claim the query writes an app artifact there. |
| Open `…:1005/metrics` on the API | 🔧 The app **pushes** OTLP metrics to the collector; there is **no `/metrics`** on the API. Prometheus scrapes `otel-collector:8889`. | Show metrics in Prometheus (`:1018`) + Grafana (`:1019`), not on the API. |
| Tracing "just works" after `make up` | 🔧 `OTEL_SDK_DISABLED` **defaults to `true`**. Traces/metrics only flow when it's `false`. And Langfuse only shows **non-$0 cost** after `make lf-models` (Langfuse prices from its own model table). | In pre-flight: set `OTEL_SDK_DISABLED=false` in `.env`, `make app` to restart the api, then `make lf-models`. Verify one warm-up query produces a trace + a metric. |

**The golden thread is built around the `/v1/recommend` API call** (via Swagger), because *that* endpoint deterministically: emits the HTTP metric, produces one clean Langfuse trace, and writes a `query_history` + `usage_daily` row. The frontend is for the streaming-UX scene. (The streaming endpoint `/v1/recommend/stream` is the live token view; the structured `/v1/recommend` is the record-of-truth.)

---

## 1. Pre-flight checklist

### 1a. The day before (do NOT do this live — it's slow + costs a cent)
```bash
# 1. Enable tracing so the observability scenes have data.
#    In .env set:  OTEL_SDK_DISABLED=false
# 2. From-scratch bring-up: wipe → build all 16 → migrate → ingest corpus.
make upv                     # ~5–8 min incl. corpus embed (~$0.01 OpenAI)
# 3. Teach Langfuse its model prices (so cost shows non-$0, not $0.00).
make lf-models
# 4. Restart the api so it picks up OTEL_SDK_DISABLED=false.
make app
```
Then warm everything with **one** query (below) so caches/dashboards/traces aren't empty on camera.

### 1b. Demo-day warm-up (2 min before recording)
```bash
make up          # everything healthy (or leave the stack running overnight)
make urls        # prints every URL + credential — keep this terminal visible
make ps          # confirm all containers are Up / healthy
# Mint an API token for the Swagger scenes (auth fails closed — no bypass):
make token       # copy the JWT it prints
```

Fire **two** warm-up queries (so semantic cache + dashboards have data), e.g.:
- `light-hearted school anime with a strong female lead`
- `a slow-burn psychological thriller under 24 episodes`

### 1c. "Is it ready?" verification list (green-light gate)
- [ ] `make ps` → **every** container `Up`; `postgres`/`redis`/`localstack` show `(healthy)`; `migrate` + `sqs-init` show `Exited (0)` (one-shots — that's correct).
- [ ] `curl -s http://localhost:1005/health` → `{"status":"ok"}`; `…/ready` → `{"status":"ready"}`.
- [ ] Web app loads at **http://localhost:1006** and you can sign in (Clerk).
- [ ] Langfuse **http://localhost:1013** logs in (`admin@anime.local` / `anime-admin-1234`) and shows the `anime-recommender` project with your warm-up trace.
- [ ] Prometheus **http://localhost:1018** → **Status ▸ Targets** → `otel-collector` **UP** (and `prometheus` UP).
- [ ] Grafana **http://localhost:1019** (`admin`/`admin`) → dashboard **"API Overview"** shows non-empty panels after the warm-up queries.
- [ ] RedisInsight **http://localhost:1016** → `app-cache` connected, and you can see `resp:…` / `sem:…` / `embed:…` keys.
- [ ] MinIO **http://localhost:1012** (`minio`/`miniosecret`) → bucket `langfuse` exists with objects.
- [ ] A repeat of a warm-up query returns **noticeably faster** (cache hit).

### 1d. On-camera hygiene
- **Zoom the browser to 110–125%** and terminal font to ~16pt — client watches on a laptop.
- **Hide secrets:** don't show `.env`, the Clerk dashboard, or the raw JWT from `make token`. If you must show a `curl`, blur/redact the `Authorization: Bearer …` line.
- Close Slack/email; use a clean browser profile with only the demo tabs.
- **Tab order (left→right):** Web `1006` · Swagger `1005/docs` · Langfuse `1013` · Prometheus `1018` · Grafana `1019` · RedisInsight `1016` · MinIO `1012`. Plus one terminal.

🔧 **RISKY-ON-CAMERA — safe versions:**
- `make downv` / `make upv` **wipe volumes** (destroys the corpus, traces, Langfuse org). Never run live. Use `make up` on demo day.
- `make chaos-*` mutate `.env` and recreate containers — **always** finish with `make chaos-restore` (idempotent) before moving on. Rehearse once.
- The `make rtbf` (right-to-be-forgotten) command **deletes user data** when `DRY=0`. For the demo use the **default dry-run** (`make rtbf USER=<id>`) — it shows the plan without deleting.

---

## 2. Scene-by-scene shot list (timed storyboard — target 8–12 min main cut)

Each scene: **(a) on screen · (b) click path · (c) narration (say this) · (d) the ONE thing to make them notice.**

### S0 — Hook (0:00–0:25)
- **(a)** Web app landing page (`:1006`), clean.
- **(b)** Just the landing page; cursor idle.
- **(c)** *"This is a production-grade AI recommendation engine. A user asks in plain English, and it returns grounded, cited recommendations in about a second. But the recommendations aren't the interesting part — what makes this sellable is everything **behind** them: it's fully observable, cost-controlled, and it degrades gracefully when things fail. Let me show you the whole system, one layer at a time."*
- **(d)** Set the frame: *this is a product, not a prototype.*

### S1 — Bring the whole system to life (0:25–1:40)
- **(a)** Terminal, then `make ps` output, then Prometheus Targets.
- **(b)**
  1. Terminal: `make up` (if pre-warmed, say "it's already running — here's what came up"), then `make ps`.
  2. Point at the healthy containers.
  3. Browser → `http://localhost:1018/targets` → all **UP**.
- **(c)** *"One command brings up sixteen containers — the app, the database, the cache, the message queue, and a full observability stack. Every service has a **health check**; Docker won't route traffic to a container until it reports healthy, and it restarts anything that dies. Over here in Prometheus, every monitored target is green — the system is watching itself. To a client this means: predictable start-up, self-healing, and no 'works on my machine.'"*
- **(d)** The `(healthy)` column + all-green Targets = *self-monitoring from second one.*

### S2 — Frontend query, live streaming (1:40–2:50)
- **(a)** Web app, signed in.
- **(b)** Type a query (e.g. *"light-hearted school anime with a strong female lead"*) → submit → watch tokens stream → 3 recommendation cards with source chips → thumbs-up one.
- **(c)** *"I'll ask in natural language. Notice the answer **streams** token-by-token — the user isn't staring at a spinner. Each recommendation is **grounded**: it comes with the source it was drawn from, so the model can't just make something up. And I can give feedback — that thumbs-up goes onto a background queue for quality review, without slowing my request down."*
- **(d)** Token streaming + the source chips (**grounding = no hallucinations**).

### S3 — The golden thread (2:50–5:30) ⭐ centerpiece
> Fire the **same** query through the API and follow its single footprint across every tool.

- **(b1) Swagger** — `http://localhost:1005/docs` → `POST /v1/recommend` → **Authorize** (paste the `make token` JWT) → **Try it out** → body `{"query":"a slow-burn psychological thriller under 24 episodes"}` → **Execute**. Show the 200 + JSON (recommendations, `query_history_id`).
- **(c1)** *"Same question, straight to the API. It returns structured JSON — the recommendations plus a `query_history_id`. That one request just left a footprint in every system. Let's follow it."*
- **(b2) API logs** — terminal: `docker compose logs --tail=20 api`. Point at the JSON log line with `request_id` and `trace_id`.
- **(c2)** *"Every log line is structured JSON with a **request ID** and a **trace ID**. Sensitive fields — emails, the raw query — are redacted automatically. This one ID is the thread that ties everything together."*
- **(b3) Langfuse** — `:1013` → project `anime-recommender` → **Tracing** → newest trace → open it. Expand the spans.
- **(c3)** *"Here's that exact request as an LLM trace. I can see the retrieval step, the documents it pulled, the final prompt, which model answered, the tokens in and out, the latency of each step, and the **cost of this single request** — right down to fractions of a cent."*
- **(b4) Prometheus** — `:1018` → Graph → run `sum(rate(anime_http_requests_total{service_name="anime-api"}[5m]))` → Execute.
- **(c4)** *"The same request also incremented a metric. Prometheus **scrapes** these numbers every 15 seconds — 'scraping' just means it pulls a fresh snapshot on a schedule — and stores them as time-series I can chart and alert on."*
- **(b5) Grafana** — `:1019` → dashboard **API Overview** → point at **Request rate** and **p95 /v1/recommend** ticking.
- **(c5)** *"And here it is visualized — request rate, error rate, latency. This is the at-a-glance health of the product."*
- **(b6) RedisInsight** — `:1016` → `app-cache` → browse keys → show a `resp:…` or `sem:…` key.
- **(c6)** *"The answer was cached. If the same or a **similar** question comes in, we serve it from Redis — no LLM call, near-zero cost, single-digit milliseconds."*
- **(b7) Postgres** — terminal: `make db-shell` → `SELECT id, query, created_at FROM query_history ORDER BY created_at DESC LIMIT 1;` then `SELECT * FROM usage_daily ORDER BY updated_at DESC LIMIT 1;`
- **(c7)** *"In the database, the request wrote a **history row** — so the user can revisit it — and a **usage row** that meters exactly how many tokens and how much money this user spent today. That's how you never get a surprise bill."*
- **(b8) MinIO** — `:1012` → bucket `langfuse` → show objects.
- **(c8)** *"And the raw trace events are durably stored in object storage — so the observability data itself survives a restart."*
- **(d)** The **same request** visible in eight places → *"this is one connected system, not eight disconnected tools."*

### S4 — Observability deep-dive (5:30–8:00)

**S4a — Langfuse (the LLM lens).** `:1013` → open a trace → walk the spans.
- **(c)** *"Langfuse answers three questions a client always asks about AI: **What did it actually do?** — I can read the exact prompt and the retrieved context. **What did it cost?** — per request, per model, in dollars. **Was it fast?** — latency for each step. If a bad answer ever ships, I open the trace and see precisely why. This is what de-risks putting an LLM in front of your customers."*
- **(d)** The per-request **cost** figure + the visible **prompt/context**.

**S4b — Prometheus (the raw signal).** `:1018` → **Status ▸ Targets** (all UP), then Graph, run 2–3:
- `sum by (status_class) (rate(anime_http_requests_total{service_name="anime-api"}[5m]))` — traffic by outcome.
- `histogram_quantile(0.95, sum(rate(anime_http_duration_seconds_bucket{service_name="anime-api",route="/v1/recommend"}[5m])) by (le))` — p95 latency.
- `sum(increase(anime_llm_cost_usd_total{service_name="anime-api"}[1h]))` — spend this hour.
- **(c)** *"Prometheus is the source of truth for numbers. Targets all green means every part of the system is being measured. I can ask it anything — 'what's my 95th-percentile latency', 'how much have I spent in the last hour' — and it answers from real data."*
- **(d)** **Status ▸ Targets all UP** = nothing is unmonitored.

**S4c — Grafana (the story).** `:1019` → **API Overview** → point panel-by-panel:
- **Request rate / Request rate by route** — *"how busy are we, and where."*
- **Error rate (5xx)** — *"is anything broken right now."*
- **Latency p50/p95/p99** — *"typical vs worst-case speed — p99 is the unhappy few, and that's what churns customers."*
- **LLM spend + cost/hour by model** — *"live money. If spend spikes, I see it here before finance does."*
- **Tokens/s by direction** & **Worker jobs by outcome** — *"throughput and background-job health."*
- **Unpriced LLM calls** — *"this should always be zero — non-zero means cost is leaking unattributed."*
- **(c)** *"This is the 3-a.m. view. If I got paged, this one screen tells me in ten seconds whether it's traffic, errors, latency, or cost — and which service. That's the difference between a 5-minute fix and a 5-hour outage."*
- **(d)** The **p95 latency** panel + the **cost** panel side by side — *speed and money, always visible.*

### S5 — Data layer (8:00–9:15)
- **(a)** RedisInsight → Postgres shell → MinIO.
- **(b)**
  1. **RedisInsight** `:1016` → `app-cache` → filter keys `resp:*`, `sem:*`, `embed:*`. Then re-run a warm-up query on the frontend and show it returns faster (cache hit).
  2. **Postgres** `make db-shell` → `\dt` (list tables) → the `query_history` + `usage_daily` rows.
  3. **MinIO** `:1012` → bucket `langfuse`.
- **(c)** *"Three caching layers — exact-match, **semantic** (similar questions), and embeddings. A repeat question skips the LLM entirely: cheaper and faster. The database is designed for scale and for privacy — every row is tied to a user, which is exactly what you need to honor a 'delete my data' request under GDPR. And object storage keeps the heavy data durable."*
- **(d)** The **repeat query getting faster** (cache = lower cost + latency, live).

### S6 — Durability / resilience (9:15–11:00) ⭐ the closer's proof
> Two failures, two *correct* behaviors. Rehearse once; always `make chaos-restore` after.

**S6a — LLM provider outage → graceful degradation.**
- **(b)** Terminal: `make chaos-llm` (flips the kill switch, recreates the api, probes `/v1/recommend`). Watch it print **HTTP 200 + degraded=true + non-empty fallback**. Then check Langfuse: **zero** LLM calls / **$0** cost in that window. Then `make chaos-restore`.
- **(c)** *"Watch what happens when the AI provider goes down — or when I hit the **cost kill-switch** to stop spend. The app doesn't error. It returns a **usable list of popular anime**, clearly marked as 'not personalized right now.' The user is never staring at a broken page, and in that window our LLM spend is exactly zero. That's a deliberate fallback, not a crash."*
- **(d)** **HTTP 200, `degraded: true`** — *degrade, don't fail.*

**S6b — Database outage → correct probe behavior.**
- **(b)** Terminal: `make chaos-pg` (stops postgres). Show: `/health` stays **200** (liveness), `/ready` returns **503** (readiness), `/v1/recommend` returns a friendly 503. Then `make chaos-restore` → `/ready` back to 200.
- **(c)** *"Now I kill the database. Two different health signals do two different jobs: **liveness** stays green — the app process is fine, so Kubernetes won't needlessly restart it — while **readiness** goes red, so the load balancer stops sending it traffic until the database is back. The moment I restore it, it rejoins automatically. This is how you survive a dependency blip without a human waking up."*
- **(d)** `/health` **200** while `/ready` **503** — *the app knows the difference between 'I'm dead' and 'my dependency is dead.'*

**(Optional S6c — background resilience, verbal):** *"Behind the scenes: failed background jobs retry, and anything truly broken lands in a dead-letter queue instead of jamming the pipeline — you can see that on the 'Worker jobs by outcome' panel."*

### S7 — Close (11:00–11:45)
- **(a)** Grafana **API Overview** full dashboard (or an architecture diagram if you have one in `docs/architecture.md`).
- **(c)** *"So — recommendations that stream and cite their sources; every request traceable end-to-end across eight systems; cost metered to the cent with a hard kill-switch; graceful degradation when a provider or the database fails; and health checks that keep it self-healing. This isn't a demo that works once — it's built to run in production, to be debugged in minutes, and to never hand you a surprise bill. Happy to go as deep as you'd like on any layer."*
- **(d)** Confidence + the offer to go deeper. End on the live dashboard.

---

## 3. "How / What / Why to monitor" reference tables

### Langfuse — `http://localhost:1013` (login `admin@anime.local` / `anime-admin-1234`)
| What to open | What to point at | Why the client cares | Exact click |
|---|---|---|---|
| A trace | The span tree (retrieve → generate) | "I can see exactly what the AI did" | project `anime-recommender` ▸ **Tracing** ▸ newest trace |
| Trace ▸ generation span | Model name, input/output tokens, **cost USD**, latency | Per-request cost + prompt visibility de-risks the LLM | click the LLM span, read the right panel |
| Trace ▸ retrieval | Retrieved documents / context | Proves answers are grounded, not invented | expand the retrieval span |
| Sessions / trace list | Fallback vs escalation, which model served | Tiered routing = cheap by default, smart when needed | filter the trace list by model |

### Prometheus — `http://localhost:1018`
| What to open | What to point at | Why the client cares | Exact PromQL |
|---|---|---|---|
| **Status ▸ Targets** | `otel-collector` = **UP** | Nothing is unmonitored | (menu) Status ▸ Targets |
| Graph | Request rate | Live traffic | `sum(rate(anime_http_requests_total{service_name="anime-api"}[5m]))` |
| Graph | p95 latency on the main route | Worst-case user experience | `histogram_quantile(0.95, sum(rate(anime_http_duration_seconds_bucket{service_name="anime-api",route="/v1/recommend"}[5m])) by (le))` |
| Graph | Spend this hour | Live cost control | `sum(increase(anime_llm_cost_usd_total{service_name="anime-api"}[1h]))` |
| Graph | Error rate | Is anything broken | `sum(rate(anime_http_requests_total{service_name="anime-api",status_class="5xx"}[5m]))` |

*One-liner for "what is scraping?":* **"Prometheus pulls a fresh snapshot of the app's counters every 15 seconds and stores the history."**

### Grafana — `http://localhost:1019` (login `admin` / `admin`) → dashboard **API Overview**
| Panel | Point at | The story it tells the client | Note |
|---|---|---|---|
| Request rate | The number ticking | "here's live demand" | stat |
| Error rate (5xx) | Should be ~0 | "here's how I know it's healthy" | stat |
| p95 /v1/recommend | Under ~1s | "worst-case speed for most users" | stat |
| LLM spend (window) | Dollars | "live spend — no surprise bills" | stat |
| Unpriced LLM calls | Should be **0** | "no cost is leaking unattributed" | stat |
| Latency percentiles | p50/p95/p99 lines | "typical vs the unhappy few — p99 is what churns" | timeseries |
| LLM cost/hour by model | Per-model $/hr | "which model is spending my money" | timeseries |
| Worker jobs by outcome | processed/failed/poison | "background jobs are healthy; failures go to a DLQ, not a crash-loop" | timeseries |
| Scrape target up | Should be `1` | "the monitoring itself is alive" | timeseries |

🔧 There is **no** cache-hit-rate or queue-depth panel here — demo cache in RedisInsight, and queue health via **Worker jobs by outcome** + LocalStack SQS.

---

## 4. Talking-points cheat sheet (capability → client value, plain language)

| Capability (real, in the repo) | Say this to the client |
|---|---|
| Token streaming + grounded, cited answers | "Fast, and it can't make things up — every recommendation shows its source." |
| End-to-end trace/request IDs (logs → Langfuse → metrics) | "Any bug, I find in minutes — one ID follows the request through the whole system." |
| Per-request cost meter + `usage_daily` + kill-switch | "You'll never get a surprise bill. Spend is metered to the cent, and there's a hard off-switch." |
| Tiered LLM (cheap default → escalate → fallback) | "Cheap model for easy questions, smarter one only when needed, and a backup provider if one goes down." |
| 3-layer cache (exact / semantic / embedding) | "Repeat and similar questions cost nothing and return instantly." |
| Graceful degradation (kill switch → popular fallback, 200) | "If the AI provider fails, users still get a usable answer — the site never breaks." |
| Liveness vs readiness probes | "The app knows the difference between 'I'm down' and 'my database is down' — so it self-heals instead of thrashing." |
| Worker + DLQ + retries | "Background work retries; genuinely broken messages are quarantined, not left to jam the queue." |
| PII redaction in logs + GDPR delete path (`make rtbf`) | "We don't log personal data, and 'delete my data' is a one-command, audited operation." |
| Prometheus + Grafana + Langfuse | "You can see health, cost, and quality at a glance — and so can I at 3 a.m." |
| *(built, not in this demo)* Canary + auto-rollback (Argo Rollouts), IaC (Terraform), Helm/K8s | "We ship new versions gradually and auto-roll-back on any dip — zero-downtime deploys. The whole cloud footprint is code." |

### Likely client questions + strong answers
- **"What happens when OpenAI/Groq goes down?"** → *"You just saw it — the app degrades to a curated fallback and returns HTTP 200 with a clear 'not personalized right now' notice. Zero errors to the user, zero spend during the outage. There's also a second provider it fails over to before that."*
- **"How do you control cost / stop a runaway bill?"** → *"Three things: every request's cost is metered per user per day; there's a per-request token budget that refuses oversized prompts before we pay for them; and a kill-switch that stops all LLM spend instantly. Grafana shows live spend, and CloudWatch alarms page us at 50/75/90% of budget."*
- **"Is my users' data safe / GDPR-ready?"** → *"Personal fields are redacted from logs; secrets live in a secrets manager, never in code; and 'delete my data' is a single audited command that removes every row tied to a user — not just nulls a foreign key."*
- **"Will it scale?"** → *"The web and API scale horizontally behind a load balancer; workers auto-scale on queue depth; the database and cache are managed, replicated services. It's designed for millions — today I'm showing it on one laptop, but the same containers run on Kubernetes with autoscaling and canary deploys."*
- **"How would you debug a bad recommendation?"** → *"Open its Langfuse trace. I see the exact prompt, the documents retrieved, the model, and the output — usually the cause is obvious in under a minute. I can't do that with a black-box API."*

---

## 5. Recording logistics

- **Tool:** OBS Studio (free, best control) or Loom (fastest to share). OBS scenes: one "full screen" + one "browser only."
- **Resolution:** record at **1920×1080**; browser zoom **110–125%**, terminal **~16pt**. Cursor-highlight ON (OBS: a highlight filter; Loom has it built in).
- **Cut the long build wait:** never record `make upv` live. Either start with the stack already up ("here's what's running"), or record `make up` and **jump-cut** past the build with a title card "16 services, ~2 min → all healthy."
- **Two cuts:**
  - **Main cut (8–12 min):** S0 → S1 → S2 → S3 (golden thread) → S6 (durability) → S7. This is the sales asset — lead with the wow (golden thread) and the proof (durability).
  - **Deep-dive (20–30 min):** insert full S4 (Langfuse/Prometheus/Grafana tool-by-tool) + S5 (data layer) between S3 and S6, for the technical buyer.
- **Suggested edit order:** record S3 and S6 **first** (they're the money scenes — nail them while fresh), then the easier bookends S0/S1/S2/S7, then the S4/S5 deep-dive. Assemble in narrative order.
- **Audio:** record narration as a separate track (read §6 below) so you can re-do a line without re-shooting the screen.
- **Safety pass before publishing:** scrub the video for any frame showing `.env`, a raw JWT, or the Clerk dashboard. Redact if found.

---

## 6. Word-for-word video script (continuous narration — main 8–12 min cut)

> Read straight through; the [SCREEN: …] cues tell you what to be showing. Pause at the ⏸ marks.

**[SCREEN: web app landing page]**
"This is a production-grade AI recommendation engine. A user asks in plain English, and it returns grounded, cited recommendations in about a second. But the recommendations aren't the interesting part — what makes this a real product is everything behind them: it's fully observable, it's cost-controlled, and it degrades gracefully when things fail. Let me walk you through the whole system, layer by layer." ⏸

**[SCREEN: terminal — `make ps`, then Prometheus Targets all green]**
"One command brings up sixteen containers — the application, the database, the cache, a message queue, and a complete monitoring stack. Every service has a health check, so the system won't send traffic to anything that isn't ready, and it restarts anything that dies. And over here, every monitored target is green — the system is already watching itself. For you that means predictable start-up and self-healing, with no 'it only works on my machine.'" ⏸

**[SCREEN: web app — type the query, tokens stream, cards appear, thumbs-up]**
"Let's ask it something. 'Light-hearted school anime with a strong female lead.' Notice the answer streams in, word by word — no spinner, no dead wait. And each recommendation is grounded: it carries the source it came from, so the model can't invent a title. I'll thumbs-up this one — that feedback goes onto a background queue for quality review, without slowing my request down at all." ⏸

**[SCREEN: Swagger — POST /v1/recommend, Execute, show JSON]**
"Now the important part. I'll send the same question straight to the API. It returns clean, structured data — the recommendations plus an ID for this request. That single request just left a footprint in every part of the system. Let me follow that one footprint everywhere it went." ⏸

**[SCREEN: terminal — docker compose logs api, point at request_id/trace_id]**
"First, the logs. Every line is structured, with a request ID and a trace ID — and sensitive fields like emails and the query text are automatically redacted. This one ID is the thread that ties the whole system together."

**[SCREEN: Langfuse — open the trace, expand spans]**
"Here's that exact request as an AI trace. I can see the retrieval step, the documents it pulled, the final prompt, which model answered, the tokens in and out, the time each step took — and the cost of this single request, down to a fraction of a cent."

**[SCREEN: Prometheus — run the request-rate query]**
"That same request also moved a metric. Prometheus pulls a fresh snapshot of these numbers every fifteen seconds and stores the history — so I can chart it and alert on it."

**[SCREEN: Grafana — API Overview, point at request rate + p95]**
"And here it is, visualized — request rate, error rate, latency. This is the health of the product at a glance."

**[SCREEN: RedisInsight — show a resp:/sem: cache key]**
"The answer was also cached. If the same, or even a similar, question comes in, we serve it straight from memory — no AI call, basically free, in milliseconds."

**[SCREEN: Postgres shell — query_history + usage_daily rows]**
"In the database, the request wrote a history row, so the user can revisit it — and a usage row that meters exactly how many tokens and how much money that user spent today. That is how you never get a surprise bill." ⏸

"So that's one request, visible in eight different systems — and it's genuinely one connected product, not eight tools bolted together." ⏸

**[SCREEN: Langfuse trace, lingering on cost + prompt]**
"Let me stay in the AI trace for a second, because this is what de-risks putting a model in front of your customers. It answers the three questions you'll always ask: what did it actually do — I can read the real prompt and context; what did it cost — per request, in dollars; and was it fast. If a bad answer ever ships, I open this and see exactly why." ⏸

**[SCREEN: Grafana — pan across the dashboard]**
"And this is the three-a.m. view. If I got paged, this one screen tells me in ten seconds whether the problem is traffic, errors, latency, or cost — and which service. That's the difference between a five-minute fix and a five-hour outage. Notice the live spend panel, and this one — unpriced calls — which should always read zero; if it doesn't, money is leaking unattributed, and I'd know immediately." ⏸

**[SCREEN: terminal — `make chaos-llm`, show 200 + degraded=true]**
"Now let me prove it's durable, not a toy. I'm going to simulate the AI provider going completely down — this is also exactly what my cost kill-switch does. Watch: the app does not error. It returns a usable list of popular anime, clearly marked as 'not personalized right now,' with an HTTP 200. And during this window, our AI spend is exactly zero. That's a deliberate fallback — degrade the request, never fail it." ⏸ **[SCREEN: `make chaos-restore`]** "And restored."

**[SCREEN: terminal — `make chaos-pg`, show /health 200, /ready 503]**
"One more — I'll kill the database. Two health signals now do two different jobs. Liveness stays green: the app itself is fine, so Kubernetes won't pointlessly restart it. But readiness goes red, so the load balancer stops sending it traffic until the database recovers. The instant I bring the database back, it rejoins on its own. That's how you ride out a dependency blip without waking anyone up." ⏸ **[SCREEN: `make chaos-restore`, /ready 200]** "Back to healthy."

**[SCREEN: Grafana API Overview, full]**
"So, to bring it together: recommendations that stream and cite their sources; every request traceable end-to-end across the whole system; cost metered to the cent with a hard kill-switch; graceful degradation when a provider or the database fails; and health checks that keep it self-healing. This isn't a demo that works once — it's built to run in production, to be debugged in minutes, and to never hand you a surprise bill. I'm happy to go as deep as you'd like on any single layer." ⏸ **[END]**

---

*Grounding note: URLs, ports, credentials, service names, metric names (`anime_http_requests_total`, `anime_http_duration_seconds_bucket`, `anime_llm_cost_usd_total`, …), the "API Overview" Grafana dashboard, and the `make chaos-llm` / `chaos-pg` / `chaos-restore` behaviors are all taken directly from the repository (`Makefile`, `infra/compose/*.yml`, `infra/observability/*`, `packages/core/src/anime_core/observability/metrics.py`, `scripts/chaos/*`). If you rename a port or a dashboard, update this runbook to match.*
