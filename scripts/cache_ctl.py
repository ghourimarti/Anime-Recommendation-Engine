#!/usr/bin/env python
"""Inspect and clear the answer cache so the SAME queries can be re-tested as fresh.

The cache is a feature worth keeping and an obstacle to re-testing: ask a question
twice and the second answer comes from Redis without touching retrieval, the router
or any model. A battery re-run against a warm cache proves nothing -- measured here
2026-09-20, a full re-run reported "cache events: nothing moved", "routing decisions:
nothing moved" and identical stage counts, because every probe was a hit.

This NEVER uses FLUSHALL/FLUSHDB and never touches anything but answer keys.

KEY LAYOUT (read from the running app, not guessed)
---------------------------------------------------
  resp:{CORPUS_VERSION}:{tenant|anon}:{sha256(normalize_query(q))}   24h TTL
  embed:{sha256(text)}                                               no TTL
  quota:{user_id}:{YYYY-MM-DD}                                       <- NOT a cache

`quota:*` uses a different prefix on purpose, so clearing answers leaves rate-limit
and daily-usage counters intact. That is what makes it safe to run mid-battery.

CORPUS_VERSION is read from the API container rather than assumed: a guessed prefix
silently deletes nothing, and a cache-clear that no-ops turns every later assertion
into a lie.

  python scripts/cache_ctl.py --ls              what is cached right now
  python scripts/cache_ctl.py --clear           drop ANSWERS (resp:*) only
  python scripts/cache_ctl.py --clear --embeddings   also drop embed:* (costs money to refill)
"""

from __future__ import annotations

import argparse
import contextlib
import subprocess
import sys

PROJECT = "anime"


def sh(*args: str, timeout: int = 60) -> str:
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


def redis(*args: str) -> str:
    return sh("docker", "exec", f"{PROJECT}-redis", "redis-cli", *args)


def corpus_version() -> str:
    """Ask the container, never guess. An unset value means the app's own default."""
    v = sh("docker", "exec", f"{PROJECT}-api", "printenv", "CORPUS_VERSION").strip()
    return v or "v1"


def scan(pattern: str) -> list[str]:
    out = redis("--scan", "--pattern", pattern)
    return [k.strip() for k in out.splitlines() if k.strip()]


def delete(keys: list[str], label: str) -> int:
    """Delete in batches. A single DEL with thousands of args overflows argv."""
    removed = 0
    for i in range(0, len(keys), 400):
        batch = keys[i : i + 400]
        out = redis("DEL", *batch)
        # A batch that returns nothing (redis-cli died, empty batch) must not abort the
        # rest -- a partial clear is still a clear, and the printed count stays honest.
        with contextlib.suppress(ValueError, IndexError):
            removed += int(out.strip().splitlines()[-1])
    print(f"  cleared {removed} {label} key(s)")
    return removed


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--ls", action="store_true", help="list what is cached")
    ap.add_argument("--clear", action="store_true", help="drop cached ANSWERS")
    ap.add_argument(
        "--embeddings",
        action="store_true",
        help="with --clear, also drop embed:* (refilling costs OpenAI calls)",
    )
    args = ap.parse_args()

    if not (args.ls or args.clear):
        ap.print_help()
        return 2

    if redis("ping") != "PONG":
        print("  redis unreachable -- is the stack up? (make up)", file=sys.stderr)
        return 1

    cv = corpus_version()
    resp_pat = f"resp:{cv}:*"
    resp = scan(resp_pat)
    # Belt and braces: if the versioned prefix matches nothing but bare resp:* does,
    # the app is writing under a different CORPUS_VERSION than the container reports.
    # Say so loudly -- silently clearing the wrong namespace is the failure this
    # whole script exists to prevent.
    all_resp = scan("resp:*")
    if not resp and all_resp:
        print(f"  WARN  no keys under {resp_pat} but {len(all_resp)} under resp:*")
        print("        the app is writing a different CORPUS_VERSION than the container")
        print("        reports; clearing the broader prefix instead")
        resp, resp_pat = all_resp, "resp:*"

    emb = scan("embed:*")
    quota = scan("quota:*")

    if args.ls:
        print(f"  CORPUS_VERSION : {cv}")
        print(f"  answers        : {len(resp):>5}   ({resp_pat})")
        print(f"  embeddings     : {len(emb):>5}   (embed:*)")
        print(f"  quota/usage    : {len(quota):>5}   (quota:*)  <- never cleared here")
        if resp[:3]:
            print("  sample answer keys:")
            for k in resp[:3]:
                print(f"    {k[:88]}")
        return 0

    print(f"  CORPUS_VERSION : {cv}")
    delete(resp, f"answer ({resp_pat})")
    if args.embeddings:
        delete(emb, "embedding (embed:*)")
    else:
        print(
            f"  kept    {len(emb)} embedding key(s) -- refilling them costs OpenAI calls;"
            " pass --embeddings to drop them too"
        )
    print(f"  kept    {len(quota)} quota key(s) -- rate limits and daily usage survive")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
