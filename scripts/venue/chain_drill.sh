#!/usr/bin/env bash
# Failover drill for the serving chain: venue -> groq -> openai.
#
# The only exercise that proves the chain is wired, rather than configured. Every other
# check in this repo reads a counter; this one breaks something and watches what happens.
#
#   bash scripts/venue/chain_drill.sh          # ~3 minutes, always restores state
#   make chain-drill
#
# WHAT IT ASSERTS, and why it is not the 503 you may expect
# ---------------------------------------------------------
# A RAG system with no model must not invent prose. P1 satisfies that by DEGRADING rather
# than erroring: with every tier down, service.py catches at the LLM boundary and returns
# `popular_fallback(DEGRADED_NOTICE)` -- HTTP 200, `degraded: true`, an honest notice, and
# items that are REAL corpus titles. So the assertion here is not "503"; it is
# "200, degraded, and every title it named actually exists in the catalogue". Those are
# different contracts and only one of them is P1's. Asserting the other would fail the
# system for behaving as designed.
#
# THREE WAYS THIS DRILL CAN LIE, all handled below
# ------------------------------------------------
# 1. An injection that did not land. Removing a leg from config makes it ABSENT, which
#    tests configuration, not resilience. A blackhole makes it FAIL. Every injection is
#    verified from inside the container, and a step that cannot prove its fault landed
#    prints "this step proves nothing" rather than a green tick.
# 2. Connection pooling. httpx keeps idle connections and consults DNS only when opening a
#    NEW one, so a request can ride the existing socket straight past /etc/hosts. We wait
#    past the keepalive before asserting anything.
# 3. The response cache. Ask the same question twice and Redis answers without touching a
#    venue at all. Every step clears cached answers AND uses a different question.
#
# WHY 127.0.0.2 AND NOT 127.0.0.1
# --------------------------------
# The api container's own uvicorn listens on :8000, and the venue is reached at
# http://anime-venue:8000/v1. Mapping that name to 127.0.0.1 would point the venue client
# at THIS APP -- the "outage" would really be a 404 from ourselves, which still fails over
# and would still look green while proving nothing about the venue. 127.0.0.2 is loopback
# with nothing bound, so the connection is refused immediately and for the right reason.
set -uo pipefail

API_CONTAINER="${API_CONTAINER:-anime-api}"
REDIS_CONTAINER="${REDIS_CONTAINER:-anime-redis}"
PG_CONTAINER="${PG_CONTAINER:-anime-postgres}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BLACKHOLE_IP="127.0.0.2"
POOL_DRAIN_SECONDS="${POOL_DRAIN_SECONDS:-8}"

# Strip the INLINE COMMENT. .env carries `API_PORT=1005   # 4. FastAPI backend`, and a
# bare `cut -d= -f2` hands that whole tail to curl, which then cannot connect and
# reports HTTP 000 on every step -- including the baseline, so the drill fails the app
# for its own parsing bug. scripts/_inspect_common.py's loader already handles this;
# this was the same bug, re-introduced by parsing .env a second time in shell.
API_PORT="$(grep -E '^API_PORT=' "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2- | sed 's/#.*$//' | tr -d '[:space:]')"
API_PORT="${API_PORT:-1005}"
API="http://localhost:${API_PORT}"

VENUE_HOST="anime-venue"
GROQ_HOST="api.groq.com"
OPENAI_HOST="api.openai.com"

BODY=""
HTTP_CODE=""
PASS=0
FAIL=0
INCONCLUSIVE=0

say()  { printf '%s\n' "$*"; }
ok()   { PASS=$((PASS + 1)); printf '  [ ok ] %s\n' "$*"; }
bad()  { FAIL=$((FAIL + 1)); printf '  [FAIL] %s\n' "$*"; }
skip() { INCONCLUSIVE=$((INCONCLUSIVE + 1)); printf '  [ -- ] %s\n' "$*"; }

# ── restore, unconditionally ─────────────────────────────────────────────────
# Runs on normal exit, on Ctrl-C, and on an unexpected error. A drill that leaves the
# hosts file poisoned has broken the stack it was meant to test.
restore_all() {
    # NOT `sed -i`. /etc/hosts is a Docker BIND MOUNT, so sed's atomic
    # write-temp-then-rename fails with "cannot rename /etc/sedXXXX: Device or resource
    # busy" -- and it fails QUIETLY behind the redirect, which is how the first run of
    # this drill left all three legs blackholed after it claimed to have restored them.
    # Rewriting through `> /etc/hosts` truncates the existing inode instead of replacing
    # it, which the mount permits.
    local strip="grep -v -e '${VENUE_HOST}' -e '${GROQ_HOST}' -e '${OPENAI_HOST}' /etc/hosts > /tmp/hosts.clean && cat /tmp/hosts.clean > /etc/hosts && rm -f /tmp/hosts.clean"
    docker exec -u root "$API_CONTAINER" sh -c "$strip" >/dev/null 2>&1 || true
    # Leaving the stack poisoned is worse than any failed assertion, so say so loudly.
    if docker exec "$API_CONTAINER" grep -q -e "${VENUE_HOST}" -e "${GROQ_HOST}" -e "${OPENAI_HOST}" /etc/hosts 2>/dev/null; then
        printf '\n  !! /etc/hosts COULD NOT BE RESTORED — the stack is still blackholed.\n'
        printf '  !! Fix it with:\n'
        printf '  !!   docker exec -u root %s sh -c "%s"\n' "$API_CONTAINER" "$strip"
    fi
}

trap 'restore_all' EXIT INT TERM

inject() {
    docker exec -u root "$API_CONTAINER" sh -c \
        "echo '${BLACKHOLE_IP} $1' >> /etc/hosts" >/dev/null 2>&1
}

# Prove the fault landed. An unverified injection turns a green result into a lie.
injection_landed() {
    local host="$1" got
    got="$(docker exec "$API_CONTAINER" getent hosts "$host" 2>/dev/null | awk '{print $1}' | head -1)"
    [ "$got" = "$BLACKHOLE_IP" ]
}

clear_cache() {
    (cd "$REPO" && python scripts/cache_ctl.py --clear >/dev/null 2>&1) || true
}

mint_token() {
    # Clerk session tokens live ~60s and each step takes longer than that, so this is
    # re-minted per step rather than once up front.
    (cd "$REPO" && uv run python scripts/dev_token.py 2>/dev/null | tail -1 | tr -d '\r')
}

# Ask one question, tagged with a request id we can find in the logs afterwards. The
# response body carries no venue field, so the log line for THIS request is the only
# immediate evidence of which leg served -- Prometheus is a scrape behind.
# BODY is held in a variable, not a temp file. `curl -o /tmp/x` under Git Bash writes
# through MSYS path translation while `python` then resolves /tmp/x by Windows rules, so
# the two disagree about which file that is: the first version of this drill read an empty
# body every time. That produced false FAILs (no recommendations in a healthy baseline)
# AND a false PASS ("not degraded" passed because the field read as empty rather than
# False), which is the worse half. Keeping it in memory removes the question.
ask() {
    local rid="$1" query="$2" token raw
    token="$(mint_token)"
    raw="$(curl -s -m 180 -w '\n%{http_code}' \
        -X POST "${API}/v1/recommend" \
        -H 'content-type: application/json' \
        -H "authorization: Bearer ${token}" \
        -H "x-request-id: ${rid}" \
        -d "{\"query\": $(python -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$query")}" \
        2>/dev/null)"
    # Assigned, never printed. `CODE="$(ask ...)"` runs this in a SUBSHELL, and the BODY
    # set there dies with it — which is why moving the body out of a temp file changed
    # nothing on its own: it was being parsed correctly and then discarded.
    BODY="${raw%$'\n'*}"
    HTTP_CODE="${raw##*$'\n'}"
}

logs_for() {
    docker logs "$API_CONTAINER" 2>&1 | grep -F "$1" || true
}

body_field() {
    BODY="${BODY:-}" python - "$1" <<'PY' 2>/dev/null
import json, os, sys
try:
    d = json.loads(os.environ.get("BODY") or "")
except Exception:
    print(""); raise SystemExit
key = sys.argv[1]
v = len(d.get("recommendations") or []) if key == "n_items" else d.get(key)
print("" if v is None else v)
PY
}

titles_exist_in_corpus() {
    # The heart of the no-model assertion: with every tier down the app may still answer,
    # but every title it names must be one the catalogue actually holds. A name that is
    # not in the corpus would mean prose was generated with no model behind it.
    local missing
    missing="$(BODY="${BODY:-}" python - <<'PY' 2>/dev/null
import json, os, subprocess
try:
    d = json.loads(os.environ.get("BODY") or "")
except Exception:
    print("UNREADABLE"); raise SystemExit
titles = [r.get("title", "") for r in (d.get("recommendations") or [])]
if not titles:
    print(""); raise SystemExit
out = subprocess.run(
    ["docker", "exec", "anime-postgres", "psql", "-U", "anime", "-d", "anime",
     "-t", "-A", "-c", "select name from anime_titles;"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
)
corpus = {line.strip() for line in (out.stdout or "").splitlines() if line.strip()}
print(", ".join(t for t in titles if t not in corpus))
PY
)"
    echo "$missing"
}

step_header() {
    say ""
    say "─── $1 ───────────────────────────────────────────────"
}

# Each step uses a DIFFERENT in-corpus question. Combined with the cache clear, that makes
# a cached answer unable to masquerade as a live one.
# Q2 is the CLEAR-CLASS query, and it belongs on the venue step specifically: routing
# only sends high-confidence queries to the self-hosted venue, so a vaguer one goes
# straight to the hosted chain and step 2 proves nothing about failover. Measured at
# +4.083 logit in S21.4a and verified routing to the venue on 2026-09-20. The baseline
# does not need the venue, so it takes the weaker one.
Q1="a cheerful school club comedy with quirky girls"
Q2="relaxing slice of life comedy about quirky high school girls"
Q3="space western with a jazz soundtrack"
Q4="lighthearted comedy about high school friends"
Q5="cooking competition with high stakes"

say ""
say "  ══════════════════════════════════════════════════════════════════"
say "  SERVING CHAIN FAILOVER DRILL   venue -> groq -> openai"
say "  Breaks each leg for real, verifies the break landed, and restores."
say "  ══════════════════════════════════════════════════════════════════"

restore_all   # start from a known-clean hosts file

# ── Step 1 — baseline ────────────────────────────────────────────────────────
step_header "1. baseline: nothing broken"
clear_cache
RID="drill1$(date +%s)"
ask "$RID" "$Q1"; CODE="$HTTP_CODE"
[ "$CODE" = "200" ] && ok "HTTP 200" || bad "HTTP $CODE (expected 200)"
[ "$(body_field n_items)" -gt 0 ] 2>/dev/null \
    && ok "answered with $(body_field n_items) recommendation(s)" \
    || bad "no recommendations in a healthy baseline"
if logs_for "$RID" | grep -q 'failed\|raised'; then
    bad "a failure was logged with nothing broken: $(logs_for "$RID" | grep -o 'venue .* failed\|primary LLM .* raised' | head -1)"
else
    ok "no venue or tier failure logged"
fi

# ── Step 2 — the self-hosted venue is down ───────────────────────────────────
step_header "2. venue blackholed -> expect fall-through to groq"
inject "$VENUE_HOST"
if injection_landed "$VENUE_HOST"; then
    ok "injection landed: ${VENUE_HOST} -> ${BLACKHOLE_IP}"
    say "        waiting ${POOL_DRAIN_SECONDS}s for pooled connections to expire…"
    sleep "$POOL_DRAIN_SECONDS"
    clear_cache
    RID="drill2$(date +%s)"
    ask "$RID" "$Q2"; CODE="$HTTP_CODE"
    [ "$CODE" = "200" ] && ok "HTTP 200 (still served)" || bad "HTTP $CODE (expected 200)"
    if logs_for "$RID" | grep -q 'venue .* failed'; then
        ok "venue attempted and fell through: $(logs_for "$RID" | grep -o 'venue [^ ]* failed' | head -1)"
    elif logs_for "$RID" | grep -q 'hosted'; then
        skip "routing chose hosted for this query, so the venue was never tried — THIS STEP PROVES NOTHING"
    else
        skip "no venue attempt recorded for this query — routing sent it hosted; THIS STEP PROVES NOTHING"
    fi
else
    skip "injection did NOT land (${VENUE_HOST} still resolves elsewhere) — THIS STEP PROVES NOTHING"
fi

# ── Step 3 — venue and groq are both down ────────────────────────────────────
step_header "3. venue + groq blackholed -> expect openai"
inject "$GROQ_HOST"
if injection_landed "$GROQ_HOST"; then
    ok "injection landed: ${GROQ_HOST} -> ${BLACKHOLE_IP}"
    say "        waiting ${POOL_DRAIN_SECONDS}s for pooled connections to expire…"
    sleep "$POOL_DRAIN_SECONDS"
    clear_cache
    RID="drill3$(date +%s)"
    ask "$RID" "$Q3"; CODE="$HTTP_CODE"
    [ "$CODE" = "200" ] && ok "HTTP 200 (still served)" || bad "HTTP $CODE (expected 200)"
    if logs_for "$RID" | grep -q 'primary LLM .* raised'; then
        ok "groq failed and the chain fell back to openai"
    else
        skip "no groq failure logged for this request — THIS STEP PROVES NOTHING"
    fi
    [ "$(body_field degraded)" = "True" ] \
        && bad "degraded with openai still available — the chain gave up early" \
        || ok "not degraded: a live tier answered"
else
    skip "injection did NOT land (${GROQ_HOST}) — THIS STEP PROVES NOTHING"
fi

# ── Step 4 — every tier is down. THE assertion. ──────────────────────────────
step_header "4. all three blackholed -> honest degradation, never invention"
inject "$OPENAI_HOST"
if injection_landed "$OPENAI_HOST"; then
    ok "injection landed: ${OPENAI_HOST} -> ${BLACKHOLE_IP}"
    say "        waiting ${POOL_DRAIN_SECONDS}s for pooled connections to expire…"
    sleep "$POOL_DRAIN_SECONDS"
    clear_cache
    RID="drill4$(date +%s)"
    ask "$RID" "$Q4"; CODE="$HTTP_CODE"
    # P1 degrades rather than erroring. 200 is correct HERE; what must never happen is
    # confident prose with no model behind it.
    [ "$CODE" = "200" ] && ok "HTTP 200 (degrades, does not error)" \
        || bad "HTTP $CODE (P1's contract is 200 + popular fallback, not an error)"
    [ "$(body_field degraded)" = "True" ] \
        && ok "degraded: true — the response admits it could not generate" \
        || bad "degraded flag not set with every tier down — the failure is invisible to the client"
    [ -n "$(body_field notice)" ] \
        && ok "notice present: $(body_field notice | cut -c1-58)…" \
        || bad "no notice explaining the degradation"
    if logs_for "$RID" | grep -q 'all LLM tiers failed'; then
        ok "all tiers were tried and all failed"
    else
        skip "no 'all LLM tiers failed' line — a tier may still have been reachable"
    fi
    MISSING="$(titles_exist_in_corpus)"
    if [ "$MISSING" = "UNREADABLE" ]; then
        bad "response body unreadable — cannot verify titles"
    elif [ -z "$MISSING" ]; then
        ok "every title returned exists in the corpus — nothing was invented"
    else
        bad "TITLES NOT IN THE CORPUS with no model available: ${MISSING}"
    fi
else
    skip "injection did NOT land (${OPENAI_HOST}) — THIS STEP PROVES NOTHING"
fi

# ── Step 5 — recovery ────────────────────────────────────────────────────────
# Recovery is half the drill. A chain that fails over and never comes back has merely
# moved the outage.
step_header "5. restored -> expect a normal answer again"
restore_all
if injection_landed "$VENUE_HOST" || injection_landed "$GROQ_HOST" || injection_landed "$OPENAI_HOST"; then
    bad "hosts file still poisoned after restore"
else
    ok "hosts file clean: all three resolve normally again"
fi
say "        waiting ${POOL_DRAIN_SECONDS}s for pooled connections to expire…"
sleep "$POOL_DRAIN_SECONDS"
clear_cache
RID="drill5$(date +%s)"
ask "$RID" "$Q5"; CODE="$HTTP_CODE"
[ "$CODE" = "200" ] && ok "HTTP 200" || bad "HTTP $CODE after restore"
[ "$(body_field degraded)" = "True" ] \
    && bad "still degraded after restore — the chain has not recovered" \
    || ok "not degraded: the chain recovered"

say ""
say "  ══════════════════════════════════════════════════════════════════"
say "  ${PASS} passed    ${FAIL} FAILED    ${INCONCLUSIVE} proved nothing"
say "  ══════════════════════════════════════════════════════════════════"
say ""
say "  Note: the kill switch (make llm-off) is NOT a venue failure. It stops"
say "  generation before the chain is consulted, so no leg is tried and no"
say "  breaker moves. Running it alongside this drill tells you nothing."
say ""
exit "$FAIL"
