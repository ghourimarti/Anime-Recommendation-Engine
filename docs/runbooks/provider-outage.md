# Runbook — LLM Provider Outage

When Groq (primary) or OpenAI (fallback) is degraded, your job is to confirm
the fallback fired, the user-visible degradation is correct, and the on-call
clock starts only if both providers are out.

**Severity matrix:**

| Condition | Severity | Page on-call? |
|---|---|---|
| Groq 5xx > 5% for 5 min, OpenAI healthy | P2 — degraded, no user impact (fallback covers) | No, but acknowledge |
| Both providers 5xx > 5% | P1 — user-visible 503s | Yes |
| Groq 4xx (rate limit) > 5% | P2 — over-quota, possibly cost-side | Check cost-spike runbook first |

---

## 1. Symptoms

Any of:
- Grafana → "API latency" dashboard: `http_req_duration{route="/v1/recommend"}` p95 spike.
- Grafana → "LLM calls (Langfuse)" panel: `langfuse_llm_calls_failed_total{provider="groq"}` rate > 5%.
- App logs (structured, JSON): `event="llm.fallback.fired" provider_from="groq" provider_to="openai"` rate elevated.
- Users report "service temporarily unavailable" if BOTH providers are down.

---

## 2. Confirm the fallback chain actually fired

Check the fallback order: Groq → OpenAI → cached "popular this week" → friendly error.

```bash
# 1. Last 100 LLM calls and their providers (Langfuse via API)
curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "$LANGFUSE_URL/api/public/traces?limit=100" \
  | jq '.data[] | {ts: .timestamp, model: .metadata.model, success: .metadata.success}'

# 2. Circuit breaker state from the API
curl -s "$BASE_URL/v1/internal/circuit-breakers"   # if exposed
# OR check structured logs:
docker compose logs api | grep '"event":"circuit_breaker"' | tail -50
```

Expected: a clear transition from `groq` to `openai` in the timeline. If
you see `provider=groq` consistently failing AND no `provider=openai`
successes, **the fallback chain is broken** — escalate to dev.

---

## 3. Cross-check the provider's own status

| Provider | Status page |
|---|---|
| Groq | https://groqstatus.com |
| OpenAI | https://status.openai.com |
| Anthropic (if added later) | https://status.anthropic.com |

If both are red, this is a black-swan; skip to §5 (cached popular).

---

## 4. Mitigations (in order)

### 4a. Confirm circuit breaker opened (auto)

The pybreaker breaker for the failing provider should open after N consecutive
failures (configurable in `packages/core/resilience.py`). Once open, calls
short-circuit immediately to the next fallback. **No human action required**
unless the breaker is misconfigured.

### 4b. Force route to the healthy provider (manual override)

If circuit breakers are misbehaving, you can pin the LLM router:

```bash
# Update the live env (K8s secret + restart)
kubectl set env deploy/anime-api LLM_FORCE_PROVIDER=openai -n anime-prod
kubectl rollout restart deploy/anime-api -n anime-prod
```

After Groq recovers:
```bash
kubectl set env deploy/anime-api LLM_FORCE_PROVIDER- -n anime-prod
kubectl rollout restart deploy/anime-api -n anime-prod
```

### 4c. Drain to popular cache (both providers out)

The "popular this week" cache (precomputed daily by the housekeeping worker)
is the LAST fallback. Confirm it's populated:

```bash
docker compose exec redis redis-cli --no-auth-warning GET anime:popular:this_week | jq '.items | length'
# Expect: 3 (or whatever the configured fallback count is)
```

If empty: the housekeeping worker hasn't run today. Trigger it manually:
```bash
make worker WORKER_QUEUE=housekeeping
```

### 4d. Flip the kill switch (last resort — extended outage)

If the outage will last >30 min and your error budget is being consumed too
fast, accept the degradation and flip `LLM_ENABLED=false`:

```bash
kubectl set env deploy/anime-api LLM_ENABLED=false -n anime-prod
```

All requests now return a friendly "service temporarily unavailable" instead
of fighting the provider. **Document this in the incident** — set a calendar
reminder to flip it back.

---

## 5. Post-incident

1. Open an incident postmortem doc (template in `docs/runbooks/postmortem-template.md`
   — TBD).
2. Confirm Langfuse + Grafana dashboards show the timeline clearly.
3. If the breakers fired late (high N): consider lowering the failure
   threshold in `resilience.py`.
4. If the cached fallback was empty: add a "popular cache freshness" alert
   to Grafana (target: refreshed within last 24h).

---

## 6. Design rationale

This runbook implements the operational discipline behind:
- **LLM tiering + fallback chain**
- **Failure modes & degradation**

If you find yourself wishing for a behavior the runbook can't express, that's
likely a design revision. Open a PR; don't paper over it operationally.

---

**3 a.m. review:** 2026-06-12, Zaini — verified every command is pasteable;
no "investigate with X" steps. Cross-referenced commands against `packages/core/src/anime_core/resilience.py`
and `docs/hardening/chaos-procedures.md §1b`. Severity matrix and fallback
order match the documented fallback design.
