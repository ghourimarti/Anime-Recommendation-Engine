# Demo Runbook — Expanded Scene Narration (companion to DEMO_RUNBOOK.md)

> This file **only** replaces §2 (the scene-by-scene shot list) with **richer, more
> detailed narration** in each scene's **(c)**. Everything else — pre-flight,
> monitor tables, talking points, logistics, and the continuous video script — stays
> in **[DEMO_RUNBOOK.md](DEMO_RUNBOOK.md)** (unchanged). Use this file when you want
> more to say per scene; use the main runbook's §6 for a tight continuous read.
>
> Same corrections apply (see DEMO_RUNBOOK.md §0): Grafana dashboard is **"API Overview"**
> (no cache-hit/queue-depth panel); MinIO = **Langfuse's** blob store; no `/metrics` on
> the API; `OTEL_SDK_DISABLED=false` + `make lf-models` required before recording.

---

## 2. Scene-by-scene shot list — EXPANDED narration (target 8–12 min main cut)

Format per scene: **(a) on screen · (b) click path · (c) narration — say this, expanded · (d) the ONE thing to make them notice.**

---

### S0 — Hook (0:00–0:30)
- **(a)** Web app landing page (`http://localhost:1006`), clean, cursor idle.
- **(b)** Landing page only.
- **(c)** *"What you're looking at is an AI recommendation engine — a user types what they're in the mood for, in plain English, and it comes back in about a second with a short list of grounded, cited suggestions. That part is easy to build; you can wire a demo like that in an afternoon. What you can't build in an afternoon — and what actually makes something you'd put in front of paying customers — is everything **around** the answer. So over the next few minutes I'm not going to sell you the recommendations. I'm going to show you that this is a real, operable product: I can see every request end-to-end, I know the exact cost of each one, it keeps running when a provider or the database goes down, and it heals itself. Let me take you through it one layer at a time, and by the end you'll be able to picture running this in production."*
- **(d)** Frame it: *this is a product, not a prototype — the answer is the easy 10%.*

---

### S1 — Bring the whole system to life (0:30–1:55)
- **(a)** Terminal → `make ps` output → browser at Prometheus **Status ▸ Targets** (all green).
- **(b)**
  1. Terminal: `make up` (if pre-warmed, say "it's already running — here's what came up") → `make ps`.
  2. Point at the `Up` / `(healthy)` column; note `migrate` and `sqs-init` show `Exited (0)`.
  3. Browser → `http://localhost:1018/targets` → all **UP**.
- **(c)** *"One command stands up the entire system — sixteen containers. That's the application's API, the web frontend, the background workers, the Postgres database with a vector search extension, a Redis cache, a message queue, and a full observability stack: Langfuse for AI tracing, Prometheus for metrics, and Grafana for dashboards. Notice two things here. First, every service has a **health check** — Docker won't route a single request to a container until it reports healthy, and it automatically restarts anything that crashes. So there's no 'the app is up but the database isn't ready' race, and no 3-a.m. page just to restart a hung process. Second — these two, 'migrate' and 'sqs-init', have already exited cleanly; those are one-shot setup jobs that ran the database migrations and created the message queues **before** the app was allowed to start. That ordering is deliberate. And over here in Prometheus, every monitored target is green — before I've even sent a request, the system is already watching itself. For you as the buyer, this is what 'operable' looks like: predictable start-up, self-healing, and a system that reports its own health instead of you finding out from an angry customer."*
- **(d)** The `(healthy)` column **plus** the all-green Prometheus Targets = *self-monitoring and self-healing from second one.*

---

### S2 — Frontend query, live streaming (1:55–3:15)
- **(a)** Web app, signed in, query box focused.
- **(b)** Type *"light-hearted school anime with a strong female lead"* → submit → watch tokens stream → 3 recommendation cards with source chips appear → hover a source chip → click thumbs-up on one card.
- **(c)** *"Let's use it the way a real user would. I'll describe what I want in natural language — not keywords, an actual sentence. Watch the response: it **streams in token by token**, the way you'd expect from a modern AI product. That's not cosmetic — a user who sees words appearing immediately perceives the app as fast and stays engaged, whereas a three-second spinner is where people bounce. Now look at each recommendation: it isn't just a title, it comes with the **source** it was drawn from. That's called grounding, and it's the single most important reliability feature for an AI product — the model is constrained to recommend from real, retrieved data, so it physically can't hallucinate a show that doesn't exist or invent a fake plot. If a client's customers are going to trust these recommendations, that guarantee is what earns the trust. And finally I'll give this one a thumbs-up. That feedback doesn't block my request — it's dropped onto a background queue and processed asynchronously, so the person clicking never waits for it, and the business still captures the signal for quality tracking and future personalization."*
- **(d)** Token-by-token streaming **and** the source chips — *fast to the user, and grounded so it can't make things up.*

---

### S3 — The golden thread (3:15–6:15) ⭐ centerpiece
> Fire the **same** query through the API and follow its single footprint across every tool. This is the scene that separates "nice demo" from "I trust these people to run it."

- **(b1) Swagger** — `http://localhost:1005/docs` → `POST /v1/recommend` → **Authorize** (paste the `make token` JWT — keep it off-screen) → **Try it out** → body `{"query":"a slow-burn psychological thriller under 24 episodes"}` → **Execute**. Show the `200` and the JSON: recommendations + a `query_history_id`.
- **(c1)** *"Now the part I'm actually proud of. I'll send the exact same kind of question, but this time straight to the API, so you can see the machinery. It comes back with clean, structured data — the recommendations, plus an ID that identifies this specific request. Here's the claim I want to prove to you: that one request just left a footprint in **every** part of the system, and because everything is tied together, I can follow that single footprint everywhere it went. Let me do exactly that, live."*
- **(b2) API logs** — terminal: `docker compose logs --tail=20 api`. Point at the JSON line carrying `request_id` and `trace_id`.
- **(c2)** *"First stop, the logs. Notice they're not free-text — every line is **structured JSON**, and every line carries a request ID and a trace ID. That matters for two reasons. One: sensitive fields like the user's email and the raw query text are automatically **redacted**, so we're not accidentally logging personal data — that's a compliance requirement, not a nice-to-have. Two: that trace ID is the thread that stitches the whole system together. Hold on to it — you're about to see the same identifier show up in three more tools."*
- **(b3) Langfuse** — `http://localhost:1013` → project `anime-recommender` → **Tracing** → the newest trace → open it → expand the spans (retrieval, generation).
- **(c3)** *"This is that exact request, seen as an AI trace. And this is where an AI product stops being a black box. I can see the retrieval step and the actual documents it pulled from the database. I can see the **final prompt** that went to the model — the real text, not a guess. I can see which model answered — we route cheap questions to a small fast model and only escalate to a bigger one when needed, and if a whole provider is down we fail over to a backup, and the trace tells me which path this request took. And critically, I can see the **cost of this single request** — right down to fractions of a cent — plus how long each step took. If a customer ever complains about a bad recommendation, I open its trace and the cause is usually obvious in under a minute. You cannot do that with a closed API."*
- **(b4) Prometheus** — `http://localhost:1018` → Graph → paste `sum(rate(anime_http_requests_total{service_name="anime-api"}[5m]))` → **Execute**.
- **(c4)** *"That same request also moved a number. This is Prometheus, the metrics database. The app continuously reports counters — how many requests, how long they took, how much they cost — and Prometheus **scrapes** them, which just means it pulls a fresh snapshot on a fixed fifteen-second schedule and keeps the history. Once it's a time-series, I can chart it, and more importantly I can **alert** on it — 'page me if error rate crosses one percent,' 'page me if we've spent more than the budget.'"*
- **(b5) Grafana** — `http://localhost:1019` (`admin`/`admin`) → dashboard **API Overview** → point at **Request rate** and **p95 /v1/recommend** updating.
- **(c5)** *"And here's that raw data turned into something a human reads at a glance — request rate, error rate, and the 95th-percentile latency of the main endpoint. This is the health of the product on one screen; I'll come back to it."*
- **(b6) RedisInsight** — `http://localhost:1016` → `app-cache` → Browser → filter keys `resp:*` and `sem:*` → open one.
- **(c6)** *"The answer to that request was also cached. We actually run three layers of caching: an exact-match cache for the identical question, a **semantic** cache that recognizes a **similar** question even if it's worded differently, and an embedding cache so we never re-compute the same vector twice. The payoff is direct: a repeat or near-repeat question skips the AI model entirely — it comes back in single-digit milliseconds and costs essentially nothing. That's how the unit economics stay sane at scale."*
- **(b7) Postgres** — terminal: `make db-shell` → `SELECT id, query, created_at FROM query_history ORDER BY created_at DESC LIMIT 1;` then `SELECT * FROM usage_daily ORDER BY updated_at DESC LIMIT 1;`
- **(c7)** *"In the database, the request wrote two rows. One is a **history** row — so the user can go back and see what they asked before. The other is a **usage** row that meters, per user per day, exactly how many tokens were consumed and how much money was spent. This is the foundation of billing and abuse-prevention: I can enforce a free-tier limit, I can charge accurately, and I can spot a runaway account instantly. This is precisely how you make sure a client never opens a surprise five-figure bill from their AI provider."*
- **(b8) MinIO** — `http://localhost:1012` (`minio`/`miniosecret`) → bucket `langfuse` → show objects.
- **(c8)** *"And last, the raw trace events themselves are written to durable object storage — this is the same kind of storage as Amazon S3, running locally. So even the observability data survives a restart; nothing important lives only in memory."*
- **(d)** The **same single request** visibly present in eight different tools → *"that's the whole point — this is one connected, observable system, not eight disconnected dashboards someone bolted together."*

---

### S4 — Observability deep-dive, tool by tool (6:15–8:45)
> Optional in the tight cut; essential for a technical buyer. Each sub-scene answers a question the client will ask.

**S4a — Langfuse: "what did the AI actually do, what did it cost, was it fast?"**
- **(b)** `:1013` → open a trace → walk the span tree top to bottom.
- **(c)** *"Let me linger in Langfuse, because this is what de-risks putting an AI model into your business. There are three questions every serious buyer asks about an LLM, and this tool answers all three with evidence, not promises. First — **what did it actually do?** I can read the exact retrieved context and the exact prompt, so there's no mystery about why it said what it said. Second — **what did it cost?** Every single call is priced in dollars, broken down by model, so cost is never a surprise at the end of the month; it's a number I watch per request. Third — **was it fast?** Each step has its own latency, so if something's slow I know whether it's retrieval, the model, or the network. Put together: when — not if — a bad answer ships someday, I don't guess and I don't apologize vaguely. I open the trace, I see the cause, and I fix it. That capability is the difference between an AI feature you can support and one you're scared of."*
- **(d)** The per-request **cost in USD** next to the **visible prompt/context**.

**S4b — Prometheus: "is everything measured, and can you answer any question about it?"**
- **(b)** `:1018` → **Status ▸ Targets** (all UP) → Graph, run in turn:
  - `sum by (status_class) (rate(anime_http_requests_total{service_name="anime-api"}[5m]))`
  - `histogram_quantile(0.95, sum(rate(anime_http_duration_seconds_bucket{service_name="anime-api",route="/v1/recommend"}[5m])) by (le))`
  - `sum(increase(anime_llm_cost_usd_total{service_name="anime-api"}[1h]))`
- **(c)** *"Prometheus is the source of truth for every number in the system. This screen — Status, then Targets — is my proof that nothing is flying blind: every component is being scraped and every one is green. If any single target went red, it would mean I'd stopped measuring a part of the system, which is itself an incident. And because it's all queryable, I can ask it anything, on the spot. Traffic broken down by outcome? One line. My 95th-percentile latency on the recommend endpoint? One line — this is the speed the slowest few percent of users actually feel, which is what drives churn far more than the average. How much money have I spent in the last hour? One line. This is the raw engine; the dashboards you're about to see are just the pretty face on top of it."*
- **(d)** **Status ▸ Targets, everything UP** = *nothing in this system is unmonitored.*

**S4c — Grafana: "show me the 3-a.m. view."**
- **(b)** `:1019` → **API Overview** → move panel by panel.
- **(c)** *"And this is where it all comes together for a human. Imagine I just got paged in the middle of the night. This one dashboard tells me in about ten seconds what's wrong. Up here: is traffic normal, are there errors, is latency healthy? These three answer 'is it up.' Then the money panels — live spend, and cost-per-hour broken down by model — so if spend suddenly spikes, I see it here **before** finance does. This panel, 'unpriced calls,' should always read zero; if it's ever non-zero it means we're making model calls we can't attribute a cost to — money leaking in the dark — and I'd catch it immediately. Down here, background-job health and throughput. The whole point of this screen is triage speed: instead of SSH-ing into servers and grepping logs for an hour, I glance once and I know whether it's traffic, errors, latency, or cost, and which service is responsible. That's the difference between a five-minute fix and a five-hour outage — and for a client, the difference between a blip and a bad day for their customers."*
- **(d)** The **p95 latency** panel and the **live spend** panel together — *speed and money, always on one screen.*

---

### S5 — Data layer (8:45–10:00)
- **(a)** RedisInsight → Postgres shell → MinIO, with a live cache-hit demonstration.
- **(b)**
  1. **RedisInsight** `:1016` → `app-cache` → filter `resp:*`, `sem:*`, `embed:*`. Then switch to the frontend and re-run one of the warm-up queries — call out that it returns visibly faster.
  2. **Postgres** `make db-shell` → `\dt` (six tables) → show the `query_history` and `usage_daily` rows again.
  3. **MinIO** `:1012` → bucket `langfuse`.
- **(c)** *"Let me make the caching concrete, because it's where cost and speed are won. Here are the actual cache keys. Watch this — I'll re-run a question I already asked, and it comes back noticeably faster, because it never touched the AI model; we served it straight from Redis. Multiply that across thousands of users asking overlapping questions and it's the difference between a viable product and a money pit. On the database side — six tables, and every row that carries user data is tied to a user ID. That's not incidental; it's what makes 'delete all my data,' which is a legal right under GDPR, a single clean operation instead of a frightening manual hunt through the system. And this object storage is the durable tier — the heavy trace data lives here, safe across restarts. So the data story is: fast and cheap through caching, correct and private in the database, durable in object storage."*
- **(d)** The **repeat query returning faster, live** — *caching isn't theory; watch it be cheaper and faster right now.*

---

### S6 — Durability / resilience (10:00–11:45) ⭐ the closer's proof
> Two induced failures, two **different, both-correct** behaviors. Rehearse once; **always** run `make chaos-restore` after each.

**S6a — AI provider outage → graceful degradation.**
- **(b)** Terminal: `make chaos-llm`. Watch it print **HTTP 200 + `degraded=true` + a non-empty popular fallback**. Flip to Langfuse and show **zero** LLM calls / **$0** in that window. Then `make chaos-restore`.
- **(c)** *"Now the part that actually convinces me a product is production-ready: what happens when something breaks. I'm going to simulate the AI provider going completely dark — and this is the exact same code path as our **cost kill-switch**, the emergency 'stop all AI spend' button. Watch the response carefully. The app does **not** throw an error and it does **not** show a broken page. It returns a genuinely usable list of popular anime, clearly labeled as 'not personalized right now,' with a normal HTTP 200. The user's experience gently degrades instead of collapsing. And look at Langfuse for this window — zero AI calls, zero dollars spent. That's the entire point of a kill-switch: in a cost emergency or a provider outage, we keep serving customers something useful while spending nothing. I want to be precise here, because it's a common mistake: a **503 error would be a failure**, not a success. Returning a working page is the design. That distinction — degrade the request, never fail it — is what keeps a client's customers from ever seeing a broken product."*
- **(d)** **HTTP 200 with `degraded: true`** and **$0 spend** — *degrade, don't fail; and the kill-switch really zeroes the bill.*

**S6b — Database outage → correct probe behavior.**
- **(b)** Terminal: `make chaos-pg` (stops Postgres). Show `/health` stays **200**, `/ready` returns **503**, `/v1/recommend` returns a friendly 503. Then `make chaos-restore` → `/ready` back to **200**.
- **(c)** *"One more failure, a different kind. This time I'll kill the database itself. Now watch two health signals do two completely different jobs — this is a subtle thing that separates hobby projects from production systems. The **liveness** check stays green: the application process is perfectly fine, it's only its dependency that's gone, so an orchestrator like Kubernetes correctly does **not** kill and restart the app — restarting it would fix nothing and just cause thrashing. Meanwhile the **readiness** check goes red within a few seconds, which tells the load balancer 'stop sending this instance traffic until it can actually serve.' So users get routed to healthy instances instead of hitting errors. And the instant I bring the database back, readiness flips green on its own and the instance quietly rejoins the pool — no human, no manual step. That's how a serious system rides out a dependency blip: it isolates the failure, protects the user, and self-recovers. And to be clear — this is chaos testing, not data loss: the database's data on disk is completely untouched the whole time."*
- **(d)** `/health` **200** while `/ready` **503** at the same moment — *the app knows the difference between 'I am dead' and 'my dependency is dead,' and reacts correctly to each.*

**(Optional S6c — background resilience, spoken over the Grafana worker panel):** *"And behind the scenes there's a third layer of durability: background jobs that fail are automatically retried, and any message that's genuinely broken gets moved into a dead-letter queue for inspection instead of jamming the pipeline and blocking everything behind it. You can watch that on the 'Worker jobs by outcome' panel — processed, failed, and quarantined, all visible."*

---

### S7 — Close (11:45–12:30)
- **(a)** Grafana **API Overview** full dashboard (or an architecture diagram if you keep one in `docs/`).
- **(c)** *"So let me bring it all together. You've seen recommendations that stream instantly and cite their sources, so they're fast and they can't hallucinate. You've seen a single request traced end-to-end across eight different systems, so any issue is debuggable in minutes rather than hours. You've seen cost metered to the fraction of a cent, with a hard kill-switch, so there's never a surprise bill. You've seen it survive both an AI-provider outage and a full database outage — degrading gracefully in one case, isolating and self-recovering in the other. And you've seen it monitor and heal itself from the moment it starts. None of that is a demo trick that works once. It's the difference between a proof-of-concept and something you can actually put in front of your customers and sleep at night. This same set of containers is built to run on Kubernetes with autoscaling and zero-downtime, canary deployments — today I'm just showing it to you on one laptop. I'm very happy to go as deep as you'd like on any single layer — the cost controls, the security and compliance story, the deployment pipeline, whatever matters most to you."*
- **(d)** Calm confidence + the explicit invitation to go deeper. End on the **live dashboard**, not a slide.

---

*Every URL, port, credential, service name, metric name, dashboard name, and `make chaos-*` behavior above is taken directly from the repo (`Makefile`, `infra/compose/*.yml`, `infra/observability/*`, `scripts/chaos/*`, `packages/core/src/anime_core/observability/metrics.py`). If you rename any of these, update this file and DEMO_RUNBOOK.md together.*
