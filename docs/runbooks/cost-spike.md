# Runbook — Cost Spike

CloudWatch billing alarm fired. Your job is to determine whether this is a
single-tenant runaway (cheap fix), a distributed regression (cache or routing
issue), or a real growth event (capacity decision).

**DO NOT flip the kill switch as a first step.** That's the panic button, and
it disables the product. Triage first.

---

## 1. Symptoms

| Severity | Trigger |
|---|---|
| P3 | Spend alert at 50% of monthly budget |
| P2 | Spend alert at 75% |
| P2 (acknowledge) | Spend alert at 90% |
| **P1 (page on-call)** | Spend alert at **200%** → Lambda auto-flips `LLM_ENABLED=false` |

Source channels: SNS → email + Slack `#anime-recommender-alerts`.

---

## 2. Confirm it's a real spike (not an alarm flap)

```bash
# CloudWatch billing alarm history
aws cloudwatch describe-alarms --alarm-names anime-recommender-spend-90 \
  --query 'MetricAlarms[0].StateUpdatedTimestamp'

# Live spend snapshot (today vs same hour last 7 days)
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d '7 days ago' +%F),End=$(date -u +%F) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --filter file://aws-ce-filter.json | jq '.ResultsByTime'
```

If the spend is genuinely 2× what it was last week, this is a real spike.
Continue.

---

## 3. Distinguish single-tenant vs distributed

This is the load-bearing triage decision.

### 3a. Per-tenant spend (last 24h)

```sql
-- Run via make db-shell or psql against prod RDS read replica
SELECT user_id,
       SUM(query_count)               AS queries,
       SUM(input_tokens)              AS in_tok,
       SUM(output_tokens)             AS out_tok,
       SUM(cost_usd)                  AS cost_usd
FROM   usage_daily
WHERE  day >= CURRENT_DATE - INTERVAL '1 day'
GROUP  BY user_id
ORDER  BY cost_usd DESC
LIMIT  20;
```

**Reading the result:**

| Pattern | What it means | Where to go next |
|---|---|---|
| Top 1 user accounts for >50% of cost | **Single-tenant runaway** — abuse, bot, or stuck client retry loop | §4a |
| Top 1 user accounts for <10% of cost | **Distributed regression** — cache hit rate dropped or routing changed | §4b |
| Mixed | Both — fix the runaway first, then investigate the rest | §4a then §4b |

### 3b. Cache hit rate (last 24h)

```promql
# In Grafana → Explore (Prometheus)
sum(rate(anime_cache_hits_total[1h]))
/
sum(rate(anime_cache_lookups_total[1h]))
```

Healthy baseline: ≥ 25%. If it dropped to single digits, your cache is
broken or invalidated — that's a code-side regression, NOT a usage spike.

---

## 4. Mitigations

### 4a. Single-tenant runaway

```bash
# 1. Look at the offending user's recent queries
psql ... -c "SELECT id, query, created_at FROM query_history
             WHERE user_id = '<offender>' ORDER BY created_at DESC LIMIT 20;"

# 2. Patch the per-user daily quota for THIS user (temporary)
psql ... -c "INSERT INTO user_quota_overrides (user_id, daily_limit, expires_at)
             VALUES ('<offender>', 5, NOW() + INTERVAL '7 days')
             ON CONFLICT (user_id) DO UPDATE
             SET daily_limit = EXCLUDED.daily_limit, expires_at = EXCLUDED.expires_at;"

# 3. If clearly abusive: revoke the Clerk session
# Clerk Dashboard → Users → <user_id> → Revoke sessions
```

### 4b. Distributed regression

Run the **tuning playbook** in `tests/load/scenarios.md` §7 starting at
Tier 1 (caching). The most common causes of cache-hit-rate drops:

1. A recent prompt change altered the response cache key (every query now
   misses) → revert / fix.
2. A deploy bumped `SEMANTIC_CACHE_SIMILARITY_THRESHOLD` → revert.
3. Redis got evicted (memory pressure) → check `redis-cli INFO memory`.
4. A change in the embedding model invalidated the semantic cache → expected
   right after an embedding-model change; cache warms up over hours.

### 4c. Emergency — extended budget overrun

If the 200% kill switch fires automatically:
- All requests return "service temporarily unavailable" (the friendly degraded path).
- Acknowledge the page; confirm Lambda flipped `LLM_ENABLED=false`:
  ```bash
  kubectl get deploy/anime-api -o yaml | grep LLM_ENABLED
  ```
- After triage + fix, flip back:
  ```bash
  kubectl set env deploy/anime-api LLM_ENABLED=true -n anime-prod
  ```
- Re-verify spend before unpausing — running ahead means it gets worse fast.

---

## 5. Post-incident

1. Open a postmortem with:
   - Root cause: runaway vs regression vs growth.
   - User-impact window: when did the kill switch fire (if applicable)?
   - Cost overrun in $: actual vs budget.
2. If single-tenant: add a recurring detection — `SELECT … HAVING SUM(cost_usd) >
   X` as a Grafana alert.
3. If distributed: add a cache-hit-rate threshold alert at 15% (below which
   the architecture has regressed silently).
4. If growth: this isn't an incident, it's a capacity decision. Schedule a
   budget bump + dependency review.

---

## 6. Design rationale

Implements the operational discipline behind:
- **Cost controls, layered**
- **Kill-switch graceful degradation**

The kill switch is the last line of defense, not the first. If you're flipping
it without triage, something is wrong with this runbook.

---

**3 a.m. review:** 2026-06-12, Zaini — verified the §3a single-tenant SQL
query runs against the v1 `usage_daily` schema; the §4c kill-switch flip is
the same env var (`LLM_ENABLED`) toggled by the chaos-llm script (§1a in
`docs/hardening/chaos-procedures.md`). Triage tree (§3) is the load-bearing
piece — DO NOT skip it under pressure.
