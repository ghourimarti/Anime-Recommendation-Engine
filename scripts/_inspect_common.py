"""Brutal end-to-end inspection engine, shared by both chain entrypoints.

Never asks "is the container up". That question has already lied on this stack:

  * vLLM is healthy, scrapeable, holding VRAM -- and has served ZERO requests,
    because rerank times out and the routing gate needs a confidence score that
    therefore never exists.
  * The "SGLang - engine up" panel reads green while SGLang is not running, because
    both venue rows share `max(up{job="venue-engine"})`.
  * Every dashboard panel reads "No data" when the product is completely broken,
    because OTLP creates series LAZILY -- a counter that never fired has no series
    at all, which is visually identical to a healthy idle system.

So every check reads a value that only exists if the component actually DID its
job: rows written, vectors returned, stages completed, decisions recorded,
counters incremented, a breaker that actually moved.

WHY THIS READS PROMETHEUS AND NOT /metrics
------------------------------------------
This app does not expose /metrics. It pushes OTLP to otel-collector:8889, which
re-exposes for Prometheus. So the sample-project trick of reading the app's own
endpoint (to dodge scrape lag and dead series) is unavailable, and both problems
have to be solved differently:

  scrape lag   -> wait_for_scrape() after probes, before reading counters.
  stale series -> `__name__` values persist after a series goes stale, so
                  "the name exists" never proves "the series is live".
                  series_live() checks for an actual sample.

Exit code is the number of FAILs, so it doubles as a gate.

  python scripts/inspect_stack_vllm.py
  python scripts/inspect_stack_sglang.py --section router --section retrieval
  python scripts/inspect_stack_vllm.py --no-probe     # read-only, sends nothing
  python scripts/inspect_stack_vllm.py --selftest     # prove the checks can FAIL
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PROJECT = "anime"
W = 100

# TWO compounding lags sit between an increment and a readable sample, and waiting
# for only one of them is why a probe's effect looks like "nothing moved":
#
#   app -> collector    OTEL_METRIC_EXPORT_INTERVAL_MS, 15s on this stack
#                       (the SDK default is 60s; this project tuned it down)
#   collector -> Prom   scrape_interval, 15s
#
# Worst case the two are anti-phase, so a safe wait is both intervals plus a margin.
# Measured 2026-09-20: an 18s wait read counters from BEFORE the probes and reported
# "cache events: nothing moved" while the cache had in fact served 12 hits.
OTEL_EXPORT_S = 15
PROM_SCRAPE_S = 15
SCRAPE_WAIT_S = OTEL_EXPORT_S + PROM_SCRAPE_S + 8

# A percentile over a handful of samples snaps to histogram BUCKET EDGES instead of
# describing the data. Below this count, report NOT MEASURED rather than inventing
# a verdict the data does not support.
NFR_MIN_SAMPLES = 20

# How much of the rerank stage's wall-clock must be the model itself before the number
# can be read as "the reranker is slow". Below this, the stage is mostly waiting for the
# event loop and optimising the cross-encoder buys almost nothing. Lives here, not in
# _inspect_sections, so the selftest asserts the SAME number the check applies.
MODEL_SHARE_MIN_PCT = 60.0
# compute is a SUBSET of wall-clock, so the share cannot exceed 100%. A few points of
# slack absorbs the two histograms being scraped a moment apart; beyond that the number
# is impossible and the only honest reading is "these are not comparable".
MODEL_SHARE_MAX_PCT = 110.0
# A loop lagging tens of milliseconds is running CPU work inside a coroutine. Measured
# healthy on this stack 2026-09-20: p99 3.5ms. A deliberately blocked loop: ~966ms.
LOOP_LAG_P99_MAX_S = 0.050

# Verified against the live corpus on 2026-09-20 (269 titles, classic era).
# Re-verify with scripts/inspect_stack_*.py --section data if the corpus is re-ingested.
IN_CORPUS = ("Cowboy Bebop", "Monster", "Berserk", "Slam Dunk", "Neon Genesis Evangelion")
# Counter-intuitive: Death Note and Steins;Gate are NOT in this subset. Checked, not assumed.
ABSENT = (
    "Demon Slayer",
    "Jujutsu Kaisen",
    "Chainsaw Man",
    "Frieren",
    "Attack on Titan",
    "Spy x Family",
    "Death Note",
    "Steins;Gate",
)


# ─── env ──────────────────────────────────────────────────────────────────────
def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = REPO / ".env"
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value and not value.startswith(('"', "'")):
            cut = value.find(" #")
            if cut != -1:
                value = value[:cut].rstrip()
        env[key.strip()] = value.strip('"').strip("'")
    return env


ENV = load_env()


def p(key: str, default: str) -> str:
    return ENV.get(key, "").strip() or default


API = f"http://localhost:{p('API_PORT', '1005')}"
PROM = f"http://localhost:{p('PROMETHEUS_PORT', '1018')}"
GRAF = f"http://localhost:{p('GRAFANA_PORT', '1019')}"
LANGFUSE = f"http://localhost:{p('LANGFUSE_WEB_PORT', '1013')}"


# ─── transport ────────────────────────────────────────────────────────────────
def http(
    url: str,
    *,
    timeout: float = 15.0,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    req = urllib.request.Request(url, method=method, data=body)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if body is not None and "content-type" not in {h.lower() for h in (headers or {})}:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def jget(url: str, **kw: Any) -> Any:
    code, text = http(url, **kw)
    if code != 200:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def sh(*args: str, timeout: int = 60) -> str:
    """Run a command, return stdout.

    encoding/errors are explicit: `text=True` alone decodes with the LOCALE codec
    (cp1252 on a Windows console) while docker output carries UTF-8. That raises
    UnicodeDecodeError on a reader THREAD, so the traceback prints but the call
    still returns -- the inspection appears to run while silently losing output.
    """
    try:
        r = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def psql(query: str) -> str:
    return sh(
        "docker",
        "exec",
        f"{PROJECT}-postgres",
        "psql",
        "-U",
        p("POSTGRES_USER", "anime"),
        "-d",
        p("POSTGRES_DB", "anime"),
        "-t",
        "-A",
        "-c",
        query,
    )


def redis(*args: str) -> str:
    return sh("docker", "exec", f"{PROJECT}-redis", "redis-cli", *args)


# ─── Prometheus ───────────────────────────────────────────────────────────────
def promq(expr: str) -> list[dict[str, Any]]:
    q = urllib.parse.quote(expr)
    data = jget(f"{PROM}/api/v1/query?query={q}")
    if not data or data.get("status") != "success":
        return []
    return data.get("data", {}).get("result", [])


def prom_scalar(expr: str) -> float | None:
    """None means NO SAMPLES, which is NOT the same as a bad value.

    histogram_quantile over an empty histogram returns NaN, and `nan <= 6.0` is
    False -- so an SLI nobody exercised rendered as a FAILED threshold. "Not
    measured" and "measured and bad" demand opposite actions.
    """
    rows = promq(expr)
    if not rows:
        return None
    try:
        v = float(rows[0]["value"][1])
    except (KeyError, IndexError, ValueError, TypeError):
        return None
    return None if v != v else v  # NaN != NaN


def prom_by(expr: str, *drop: str) -> dict[str, float]:
    """Instant query -> {label-signature: value}, with noise labels dropped."""
    noise = {
        "__name__",
        "job",
        "instance",
        "service_name",
        "telemetry_sdk_language",
        "telemetry_sdk_name",
        "telemetry_sdk_version",
        *drop,
    }
    out: dict[str, float] = {}
    for s in promq(expr):
        m = {k: v for k, v in s["metric"].items() if k not in noise}
        key = ",".join(f"{k}={v}" for k, v in sorted(m.items())) or "(no labels)"
        try:
            out[key] = out.get(key, 0.0) + float(s["value"][1])
        except (ValueError, TypeError):
            continue
    return out


def bucket_boundaries_stable(selector: str, window: str = "30m") -> bool | None:
    """Do this histogram's `le` boundaries look the same now as across the window?

    histogram_quantile sums buckets by `le`. If the boundaries CHANGED inside the
    window -- a container rebuilt with a different View, an instrument that was
    previously unviewed and inheriting OTel's millisecond defaults -- then
    `sum by (le)` silently merges two incompatible sets and the quantile is
    nonsense. Caught here 2026-09-20 exactly that way: the rerank split reported
    "204% model", which is impossible, because compute's old default boundaries
    (le=5,10,...,10000) were still inside the 30m window alongside the new ones.

    The check is cheap and self-controlling: an untouched histogram reports the same
    count both ways (stage_duration measured 18 and 18), a changed one does not
    (rerank_compute measured 18 now against 31 across the window).

    None means the question could not be answered, which is NOT the same as stable.
    """
    now = prom_scalar(f"count(count by (le) ({selector}))")
    across = prom_scalar(f"count(count by (le) (count_over_time({selector}[{window}])))")
    if now is None or across is None:
        return None
    return across <= now


def series_live(metric: str) -> bool:
    """A live series, not merely a remembered NAME.

    Prometheus keeps `__name__` label values for a retention window after a series
    goes stale, so enumerating names tells you what has EVER existed on this stack,
    not what exists now. Only an actual sample proves live.
    """
    return bool(promq(metric))


def wait_for_scrape(reason: str = "") -> None:
    msg = (
        f"  ..    waiting {SCRAPE_WAIT_S}s for app->collector ({OTEL_EXPORT_S}s) "
        f"+ collector->Prometheus ({PROM_SCRAPE_S}s)"
    )
    print(f"{msg} -- {reason}" if reason else msg, flush=True)
    time.sleep(SCRAPE_WAIT_S)


# ─── auth ─────────────────────────────────────────────────────────────────────
class Auth:
    """Clerk tokens live ~60s on this instance (scripts/dev_token.py docstring).

    A token minted once at start-up is reliably dead by the time a long battery
    reaches its later probes: every call 401s and it reads as an auth bug rather
    than a stopwatch. So mint lazily and re-mint on expiry.
    """

    TTL_S = 45  # re-mint before the ~60s real expiry

    def __init__(self) -> None:
        self._token: str | None = None
        self._minted_at = 0.0

    def token(self) -> str | None:
        if self._token and (time.time() - self._minted_at) < self.TTL_S:
            return self._token
        env_tok = os.environ.get("K6_AUTH_TOKEN", "").strip()
        if env_tok:
            self._token, self._minted_at = env_tok, time.time()
            return self._token
        out = sh("uv", "run", "python", str(REPO / "scripts" / "dev_token.py"), timeout=90)
        tok = (out.splitlines() or [""])[-1].strip()
        if tok and len(tok) > 50:
            self._token, self._minted_at = tok, time.time()
            return tok
        return None

    def headers(self) -> dict[str, str]:
        t = self.token()
        return {"Authorization": f"Bearer {t}"} if t else {}


AUTH = Auth()


# ─── the app ──────────────────────────────────────────────────────────────────
@dataclass
class Answer:
    code: int
    body: dict[str, Any]

    @property
    def recs(self) -> list[dict[str, Any]]:
        return self.body.get("recommendations") or []

    @property
    def refusal(self) -> str | None:
        return self.body.get("refusal")

    @property
    def degraded(self) -> bool:
        return bool(self.body.get("degraded"))

    @property
    def notice(self) -> str:
        return self.body.get("notice") or ""

    @property
    def kind(self) -> str:
        """Derived: the API returns no `kind` field, so infer it from the contract.

        Two DEGRADED paths exist and the flag alone cannot separate them -- only the
        notice text can. They have different causes and different fixes:
          retrieval_gate  "didn't find strong matches"        -> nothing scored
          llm_failed      "couldn't generate tailored ..."    -> the model call failed
        """
        if self.code == 429:
            return "quota_limited"
        if self.code != 200:
            return f"http_{self.code}"
        if self.refusal:
            return "refused"
        if self.degraded:
            n = self.notice.lower()
            if "strong match" in n:
                return "degraded:retrieval_gate"
            if "generate" in n or "tailored" in n:
                return "degraded:llm_failed"
            return "degraded:unknown"
        return "grounded" if self.recs else "no_answer"


def ask(query: str, *, timeout: float = 120.0) -> Answer:
    code, text = http(
        f"{API}/v1/recommend",
        method="POST",
        timeout=timeout,
        body=json.dumps({"query": query}).encode(),
        headers=AUTH.headers(),
    )
    try:
        return Answer(code, json.loads(text))
    except json.JSONDecodeError:
        return Answer(code, {"_raw": text[:200]})


# ─── check model ──────────────────────────────────────────────────────────────
@dataclass
class Check:
    name: str
    desired: str
    actual: str
    ok: bool | None
    note: str = ""


@dataclass
class Section:
    key: str
    title: str
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, desired: str, actual: str, ok: bool | None, note: str = "") -> None:
        self.checks.append(Check(name, desired, actual, ok, note))


@dataclass
class Ctx:
    """Shared state. Probes fire ONCE and every section reads the same results.

    Ordering used to be implicit in the sample project: a section asserted
    `refused > 0` while the refusal probes lived two sections later and had not
    run yet, so a working guardrail was reported as a FAIL above the evidence that
    it worked. Counters cannot be checked before the thing that increments them
    has happened.
    """

    engine: str  # "vllm" | "sglang"
    probe: bool = True
    keep_cache: bool = False
    results: dict[str, Answer] = field(default_factory=dict)
    before: dict[str, dict[str, float]] = field(default_factory=dict)
    after: dict[str, dict[str, float]] = field(default_factory=dict)
    warmed: bool = False


COUNTERS = {
    "stages": "sum by (stage,outcome) (anime_retrieval_stage_duration_seconds_count)",
    "llm": "sum by (model,outcome) (anime_llm_duration_seconds_count)",
    "venue": "sum by (decision) (anime_llm_venue_decisions_total)",
    "cache": "sum by (result) (anime_cache_lookups_total)",
    "refusals": "sum(anime_llm_refusals_total)",
    "http": "sum by (status_class) (anime_http_requests_total)",
    "tokens": "sum by (model,direction) (anime_llm_tokens_total)",
    "cost": "sum by (model) (anime_llm_cost_usd_total)",
    "unpriced": "sum by (model) (anime_llm_unpriced_calls_total)",
    "quota": "sum by (scope) (anime_quota_rejections_total)",
    "breakers": "sum by (breaker,state) (anime_circuit_transitions_total)",
    "confidence": "anime_retrieval_confidence_count",
}


def snapshot() -> dict[str, dict[str, float]]:
    return {k: prom_by(expr) for k, expr in COUNTERS.items()}


def delta(
    before: dict[str, dict[str, float]], after: dict[str, dict[str, float]], key: str
) -> dict[str, float]:
    b, a = before.get(key, {}), after.get(key, {})
    out: dict[str, float] = {}
    for label in set(a) | set(b):
        d = a.get(label, 0.0) - b.get(label, 0.0)
        if abs(d) > 1e-9:
            out[label] = d
    return out


def fmt(d: dict[str, float]) -> str:
    if not d:
        return "(nothing moved)"
    return "  ".join(f"{k}={v:g}" for k, v in sorted(d.items()))


# ─── render ───────────────────────────────────────────────────────────────────
def render(sections: list[Section], engine: str) -> int:
    fails = 0
    print()
    print("  " + "=" * W)
    print(f"  ANIME RECOMMENDER - FULL STACK INSPECTION   [chain: {engine} -> groq -> openai]")
    print("  Each check reads a value that exists only if the component did its job.")
    print("  " + "=" * W)
    for sec in sections:
        print()
        print(f"  {sec.title}")
        print("  " + "-" * W)
        for c in sec.checks:
            mark = "[ ok ]" if c.ok else ("[FAIL]" if c.ok is False else "[ -- ]")
            if c.ok is False:
                fails += 1
            print(f"  {mark} {c.name:<32} {c.actual}")
            if c.ok is False:
                print(f"         {'want:':<32} {c.desired}")
            if c.note:
                for i, line in enumerate(_wrap(c.note, 84)):
                    print(f"         {'why:' if i == 0 else '':<32} {line}")
    total = sum(len(s.checks) for s in sections)
    info = sum(1 for s in sections for c in s.checks if c.ok is None)
    print()
    print("  " + "=" * W)
    print(f"  {total - fails - info} passed    {fails} FAILED    {info} informational")
    print("  " + "=" * W)
    print()
    return fails


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


# ─── selftest ─────────────────────────────────────────────────────────────────
def selftest() -> int:
    """Negative controls. A check that cannot fail is decoration, not a check."""
    print()
    print("  " + "=" * W)
    print("  SELFTEST - every control below must REJECT. A pass here means the")
    print("  corresponding check is capable of failing when reality is wrong.")
    print("  " + "=" * W)
    fails = 0
    # Named rather than inlined so the comparisons read measurement-first ("5% is below
    # the floor"), which is the direction the check itself applies them in.
    starved_share_pct = 0.05 / 1.00 * 100  # a stage that is 95% waiting for the loop
    model_bound_share_pct = 2.20 / 2.30 * 100  # what this stack actually measured
    impossible_share_pct = 4.574 / 2.244 * 100  # the 204% reading that exposed the gap
    blocked_loop_s = 0.966  # reproduced in test_loop_monitor
    healthy_loop_s = 0.0035  # measured here 2026-09-20
    controls: list[tuple[str, bool, str]] = [
        (
            "scalar of a metric that does not exist returns None (not 0)",
            prom_scalar("anime_this_metric_does_not_exist_total") is None,
            "if this returned 0.0, 'not measured' would silently read as 'measured and fine'",
        ),
        (
            "series_live rejects a name with no samples",
            not series_live("anime_this_metric_does_not_exist_total"),
            "guards against the stale __name__ index reading as a live series",
        ),
        (
            "series_live accepts a real live series",
            series_live("up"),
            "the positive control: the check must also be able to PASS",
        ),
        (
            "prom_by on a bogus expression yields nothing",
            prom_by("sum by (nope) (anime_not_a_metric_total)") == {},
            "a silent {} beats an exception that aborts the whole run",
        ),
        (
            "delta detects a counter that moved",
            delta({"x": {"a": 1.0}}, {"x": {"a": 3.0}}, "x") == {"a": 2.0},
            "the arithmetic the venue/cache assertions rest on",
        ),
        (
            "the cost split rejects a stage that is mostly NOT the model",
            starved_share_pct < MODEL_SHARE_MIN_PCT,
            "5% model / 95% waiting is the loop-starved case the split exists to catch; "
            "if this threshold could not reject it, the check would bless a blocked loop",
        ),
        (
            "the cost split accepts a genuinely model-bound stage",
            model_bound_share_pct >= MODEL_SHARE_MIN_PCT,
            "the positive control, and the case actually measured here 2026-09-20 -- "
            "a check that fails on healthy data gets muted and stops being read",
        ),
        (
            "the cost split refuses a physically impossible ratio",
            impossible_share_pct > MODEL_SHARE_MAX_PCT,
            "compute is a SUBSET of wall-clock, so >100% means the two histograms are not "
            "comparable -- measured 204% on 2026-09-20 when old and new le boundaries sat "
            "in the same window. Without this bound the check PASSED on nonsense",
        ),
        (
            "the loop-lag ceiling rejects a blocked loop",
            blocked_loop_s > LOOP_LAG_P99_MAX_S > healthy_loop_s,
            "both directions in one control: the 966ms blocked loop reproduced in "
            "test_loop_monitor must fail, and the 3.5ms healthy reading must not",
        ),
        (
            "delta reports nothing when a counter is flat",
            delta({"x": {"a": 1.0}}, {"x": {"a": 1.0}}, "x") == {},
            "an unchanged counter must be visible as unchanged, not as absent",
        ),
    ]
    for name, passed, why in controls:
        mark = "[ ok ]" if passed else "[FAIL]"
        if not passed:
            fails += 1
        print(f"  {mark} {name}")
        print(f"         why: {why}")
    print()
    print(f"  {len(controls) - fails} controls passed    {fails} FAILED")
    print()
    return fails


# ─── main ─────────────────────────────────────────────────────────────────────
def main(engine: str, sections: dict[str, Any]) -> int:
    ap = argparse.ArgumentParser(
        description=f"Brutal full-stack inspection, chain: {engine} -> groq -> openai"
    )
    ap.add_argument(
        "--section", choices=sorted(sections), action="append", help="run a subset (repeatable)"
    )
    ap.add_argument("--no-probe", action="store_true", help="read-only: send no queries to the app")
    ap.add_argument(
        "--keep-cache",
        action="store_true",
        help="do NOT clear cached answers first (re-runs then prove nothing)",
    )
    ap.add_argument(
        "--selftest", action="store_true", help="run negative controls proving the checks can fail"
    )
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    ctx = Ctx(engine=engine, probe=not args.no_probe, keep_cache=args.keep_cache)
    keys = args.section or list(sections)
    built: list[Section] = []
    for k in keys:
        try:
            built.append(sections[k](ctx))
        except Exception as e:
            sec = Section(k, f"{k.upper()} (section raised)")
            sec.add(
                "section executed",
                "no exception",
                f"{type(e).__name__}: {e}",
                False,
                "a section that raises hides every check inside it",
            )
            built.append(sec)
    return render(built, engine)
