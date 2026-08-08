# Demo Video Script — Anime Recommender (Production RAG)

**Target length:** 12–14 minutes
**Audience:** a technical buyer / hiring manager deciding if you can build and *operate* real systems
**Goal:** they finish thinking *"this person has actually run production, not just followed a tutorial."*

> ⚠️ **Read `docs/inspection-report.md` before recording.** Three findings materially affect this demo:
> - **Do NOT demo Grafana** — it has zero app metrics. It will be an empty dashboard on camera.
> - **Do NOT claim a cost-per-request number** — the system currently records `$0.00`.
> - **Do NOT claim "advanced RAG beats naive"** — with the reranker timing out, success@1 delta is `+0.000`.
>
> Either **fix them first** (recommended — C1 is a one-line model swap) or **use the honest framing** in §6.

---

## 0. Pre-flight checklist (do ALL of this before you hit record)

```bash
# 1. Full stack up (16 services)
make up
make ps                      # every service Up / healthy

# 2. WARM THE CACHES — a cold first query takes 5s+ and looks bad on camera
#    Run each demo query ONCE now so the pipeline, model, and connections are hot.
JWT=$(scripts/mint_jwt.sh)   # or your token-minting method
for q in "a psychological thriller with an unreliable narrator" \
         "a samurai revenge story set in feudal Japan"; do
  curl -s -o /dev/null -X POST http://localhost:1005/v1/recommend \
    -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
    -d "{\"query\":\"$q\"}"
done

# 3. Langfuse must NOT be an empty project — the warm-up above populates it.
#    Open http://localhost:1013, log in, confirm you see POST /v1/recommend traces.

# 4. Reset the worker restart counter so it reads 0 on camera
docker compose ... up -d --force-recreate --no-deps worker

# 5. Sign in to the web app in the browser ALREADY (Clerk session live, no login on camera)
```

**Tabs to have pre-opened (in this order):**
1. Web app — <http://localhost:1006> (signed in, empty query box)
2. Terminal A — logs, ready to run `docker logs anime-api | grep <id>`
3. Langfuse — <http://localhost:1013>, on the Traces list
4. Terminal B — `psql` / `redis-cli` ready
5. VS Code — `docs/decision-log.md` open
6. Terminal C — for the chaos moment

---

## 1. Shot-by-shot storyboard

### SEGMENT 1 — The hook: it works, and it streams (0:00–1:30)
**Screen:** the web app, full screen.
**Do:** type *"a psychological thriller with an unreliable narrator"* → hit enter → let tokens stream in.
Click a thumbs-down on one card. Open **History** and show the query is there.

**Say:**
> "This is a production-grade RAG application. Multi-tenant, authenticated, streaming.
> Watch the tokens arrive — that's Server-Sent Events, not a spinner-then-dump.
> I can cancel mid-stream and it actually aborts the upstream LLM call, so I stop paying for it."

*(Hit the Stop button on a second query to show cancellation.)*

**Why first:** never open with infrastructure. Show the product working.

---

### SEGMENT 2 — Architecture in 90 seconds (1:30–3:00)
**Screen:** `docs/architecture.md` diagram, or `docs/decision-log.md` at-a-glance table.

**Say:**
> "22 architecture decisions, each with the alternatives I rejected and the trigger that would make me
> revisit it. Not 'I used LangChain' — but *why*, and what would change my mind.
> The shape: Next.js frontend talks to its own backend-for-frontend, which is the only thing that
> holds the API token. FastAPI does hybrid retrieval over pgvector, reranks, and calls a tiered LLM
> with a fallback chain. Async work goes to SQS workers. Everything is traced."

**Point at ONE decision** (e.g. D2 pgvector-not-Qdrant) and say why: *"269 titles today, 20k planned —
Qdrant would be cargo-culting. The abstraction lets me swap it in a day when the trigger fires."*

---

### SEGMENT 3 — Under the hood: one query, every layer (3:00–5:30)
**Screen:** Terminal A + Langfuse side by side.

**Do:**
```bash
# 1. run a query, grab the correlation id
curl -s -D - -o /dev/null -X POST http://localhost:1005/v1/recommend \
  -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  -d '{"query":"a samurai revenge story set in feudal Japan"}' | grep -i x-request-id

# 2. same id in the JSON logs — and it carries a trace_id
docker logs anime-api 2>&1 | grep <request_id> | head -2
```
**Then switch to Langfuse** and paste that **same `trace_id`** into the trace URL.

**Say (this is your strongest 60 seconds — slow down here):**
> "Here's the request ID from the HTTP response. Here it is in the structured JSON logs — and notice
> the logs also carry a `trace_id`. Now watch: **that same trace ID** opens the distributed trace.
> 26 spans: the HTTP request, the OpenAI embedding call, the Groq LLM call with exact token counts,
> every Redis cache operation, the Postgres connection.
> **One ID. Logs, traces, and LLM observability all line up.** When something breaks at 3am, that's
> the difference between a four-hour incident and a four-minute one."

**Also note:** *"And no PII — the user's email and query text are never written to a log line."*
(Show `docker logs anime-api | grep -c "@"` → 0.)

---

### SEGMENT 4 — The RAG pipeline + eval (5:30–7:30)
**Screen:** terminal.

**Do:** `make eval`

**Say:**
> "I don't guess at quality — I measure it. 24-query golden set, IR metrics, advanced pipeline vs a
> naive baseline. Hybrid retrieval — dense vectors plus BM25 — then a cross-encoder reranker, then MMR
> for diversity. `distinct_ratio 1.0` means no duplicate recommendations."

**⚠️ HONESTY GATE:** if you have **not** fixed C1, do **not** claim a quality lift. Say instead:
> "And I'll be straight with you: right now my reranker is timing out on real-length inputs, so the
> advanced pipeline is only matching naive at rank one. I found that by instrumenting it and running
> the eval — which is exactly the point of having an eval harness. It's a one-line model swap to fix."

*(A buyer who hears you diagnose your own bug trusts you more than one who hears a clean number.)*

**Then show grounding:** *"Zero hallucinated IDs — every recommendation is validated back against the
retrieved candidates. If the model invents an anime, we drop it."*

---

### SEGMENT 5 — 🔥 THE MONEY SHOT: kill the LLM live (7:30–9:30)
**Screen:** web app + Terminal C.

**Do:**
```bash
bash scripts/chaos/kill_llm.sh    # or: set LLM_ENABLED=false, recreate api
```
Wait for healthy (~15s), then **run a query in the browser**.

**Say:**
> "Let's break it on purpose. I'm killing the LLM provider right now.
> …
> Watch: the user does *not* get a 500. They get a 200, an honest message —
> *'we couldn't generate tailored recommendations right now, here are some widely loved anime while we
> recover'* — and a curated fallback list. The product still works."

**Then the second kill — even better:**
```bash
# invalidate the Groq key only
```
> "Now I'll corrupt just the Groq API key and leave OpenAI alive."
Run a query → **real recommendations come back, `degraded: false`**.
```bash
docker logs anime-api | grep "falling back"
# primary LLM openai/gpt-oss-20b raised (401 Invalid API Key); falling back to gpt-4o-mini
```
> "The primary provider 401'd, it failed over to OpenAI automatically, and **the user never knew.**
> That's a circuit breaker and a fallback chain, not a try/except."

**Restore:** `bash scripts/chaos/restore.sh` — and *show* it come back healthy.

**This is the most persuasive 2 minutes in the entire demo. Rehearse it.**

---

### SEGMENT 6 — Async, idempotency, and the DLQ (9:30–11:00)
**Screen:** terminal, split with `docker logs -f anime-worker`.

**Do:** click thumbs-down in the browser → watch the worker log fire.

**Say:**
> "That thumbs-down didn't block the response. It wrote to Postgres, then published a job to SQS —
> fire-and-forget, so if the queue is down the user's request still succeeds.
> A worker picks it up and writes an eval signal to Redis."

**Then prove idempotency:**
```bash
# republish the exact same job
awslocal sqs send-message --queue-url $Q --message-body '{...same idempotency_key...}'
docker logs anime-worker | tail -1
# "duplicate job feedback:1 (feedback.recorded); skipping"
```
> "SQS gives you *at-least-once* delivery — duplicates are guaranteed, not hypothetical.
> So every handler is idempotent, keyed on the feedback row ID. Same message twice, work happens once.
> And poison messages redrive to a dead-letter queue after five attempts instead of wedging the queue."

*(⚠️ If you have NOT fixed C3, do not send a malformed message on camera — it will crash-loop the worker.)*

---

### SEGMENT 7 — Security & cost controls (11:00–12:00)
**Screen:** terminal.

**Do & say:**
```bash
curl -X POST .../v1/recommend -d '{"query":"x"}'          # → 401
```
> "No token, no service — it fails closed."

```bash
# user B's history is empty even though user A has 20 queries
```
> "Multi-tenant isolation is enforced at the query layer, not filtered in the app."

```bash
curl ... -d '{"query":"<501 chars>"}'                     # → 422
```
> "Input is capped at the schema boundary, so nobody can burn my token budget with a giant prompt.
> Per-user daily quotas return a 429 with a `Retry-After`. There's a kill switch that stops all LLM
> spend instantly — you just saw it. Secrets come from AWS Secrets Manager via External Secrets
> Operator; there isn't a key in the repo or in the image."

**⚠️ Do NOT quote a cost-per-request figure** until C2 is fixed.

---

### SEGMENT 8 — Ship it: K8s, Terraform, and what's NOT deployed (12:00–13:30)
**Screen:** terminal + VS Code.

**Do:**
```bash
helm lint infra/k8s/helm/anime-recommender -f values-prod.yaml
helm template ... | kubeconform -ignore-missing-schemas -summary
cd infra/terraform/envs/dev && terraform validate
```

**Say:**
> "The whole thing is packaged: a Helm chart that deploys the API as an Argo Rollouts canary, the web
> as a Deployment with an HPA, and one worker Deployment per queue with KEDA scaling on queue depth —
> because a queue worker's load is queue depth, not CPU. Migrations run as a pre-upgrade hook, not in
> the app entrypoint, so ten replicas don't race each other. Terraform stands up VPC, EKS, RDS,
> ElastiCache, SQS, IRSA roles scoped to exact ARNs — no wildcards."

**Then the line that earns trust:**
> "And I'll be precise about what this is: the Terraform is **validated, not applied**. The Helm chart
> is **rendered, not deployed**. I have not run this on a live EKS cluster with real traffic —
> I'm not going to pretend otherwise."

---

### SEGMENT 9 — Close (13:30–14:00)
> "So: a RAG system that streams, degrades gracefully when its dependencies die, traces every request
> end-to-end through one correlation ID, isolates tenants, controls cost, and is packaged for K8s with
> progressive delivery. Built as an in-place transformation of a tutorial-grade demo, with every
> architectural decision written down — including the ones I'd revisit.
> Happy to walk through any layer in detail."

---

## 2. The 5 lines that signal senior (use them verbatim)

1. **"One trace ID ties the logs, the distributed trace, and the LLM trace together. That's the
   difference between a four-hour incident and a four-minute one."**
2. **"SQS is at-least-once, so duplicates are guaranteed, not hypothetical. Every handler is idempotent
   — I process-then-delete, never delete-then-process."**
3. **"I canary only the API. Canarying a stateless frontend or a queue worker adds rollout latency
   without adding safety — you canary what hurts users when it breaks."**
4. **"Migrations run as a release-phase hook, not in the app entrypoint — otherwise N replicas race
   each other on startup."**
5. **"My reranker is timing out on real-length inputs, so the advanced pipeline is currently only
   matching naive. I know that because I instrumented it and ran the eval."**
   *(Counter-intuitive, but the single most credibility-building sentence available to you. Buyers have
   heard a hundred flawless demos. They have never heard someone name their own live defect and its fix.)*

---

## 3. Traps to avoid

| Trap | Why it bites | Prevention |
|---|---|---|
| **Cold cache on camera** | First query = 5s+ of dead air | Warm every demo query in pre-flight |
| **Empty Langfuse project** | The money shot lands on an empty list | Warm-up run populates it; verify before recording |
| **Grafana** | **Zero app metrics — the dashboard is empty** | **Skip it entirely** (or fix C5 first) |
| **Quoting a cost number** | It records $0.00 | Don't, until C2 is fixed |
| **Expired Clerk JWT (60s!)** | Random 401 mid-demo | Re-mint immediately before each curl, or use the browser |
| **Poison-message demo** | **Crash-loops the worker (C3)** | Don't do it live until fixed |
| **Slow first embedding call** | OpenAI RTT can spike to ~1s | Warm-up; and don't narrate over it |
| **Claiming a quality lift** | success@1 delta is currently +0.000 | Use the honest framing (Segment 4) |
| **Opening with Terraform** | Nobody buys infra before they see product | Product first, always |

---

## 4. If you only have 5 minutes

Cut to: **Segment 1** (it works, it streams) → **Segment 3** (one trace ID, three tools) →
**Segment 5** (kill the LLM, watch it degrade) → the honest close.

That is the whole story: *it works, I can see inside it, and it survives its dependencies dying.*
