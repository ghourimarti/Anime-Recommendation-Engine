#!/usr/bin/env python
"""Push LLM_PRICING into Langfuse's model table.

Langfuse does NOT use our CostMeter — it computes trace cost from its own model
definitions, matched against the model name by regex. Any model it doesn't know
shows up as $0.00 in the UI, which is how the dashboard can look healthy while
real spend goes unattributed.

That gives us two price tables, and two price tables always drift. So this script
makes LLM_PRICING (the env var) the single source of truth and projects it into
Langfuse. Run it after changing a price, and in deploy after the Langfuse stack
is up:

    uv run python scripts/langfuse_models.py

Unit conversion matters: LLM_PRICING is USD per 1M tokens (how providers quote
it); Langfuse wants USD per single token. Getting this wrong by 1e6 is a very
quiet, very expensive mistake, so the conversion lives in exactly one place here.
"""

from __future__ import annotations

import os
import re
import sys
from decimal import Decimal

import httpx
from anime_core.cost_meter import PRICING_ENV_VAR, parse_pricing
from dotenv import load_dotenv

_PER_MILLION = Decimal("1000000")


def main() -> int:
    load_dotenv()
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:1013")
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not public or not secret or public.startswith("pk-lf-..."):
        print("LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set in .env", file=sys.stderr)
        return 1

    table = parse_pricing(os.environ.get(PRICING_ENV_VAR, ""))
    rc = 0
    with httpx.Client(base_url=host, auth=(public, secret), timeout=30.0) as c:
        # Existing definitions, so re-running is idempotent rather than duplicating.
        existing: dict[str, str] = {}
        r = c.get("/api/public/models", params={"limit": 100})
        if r.status_code == 200:
            for m in r.json().get("data", []):
                existing[m["modelName"]] = m["id"]

        for model, (in_per_m, out_per_m) in sorted(table.items()):
            if model in existing:
                # Prices are immutable per definition in Langfuse — replace it.
                c.delete(f"/api/public/models/{existing[model]}")
            body = {
                "modelName": model,
                # Anchor the pattern: an unanchored "gpt-4o" would also match
                # "gpt-4o-mini" and price cheap calls at the expensive rate.
                "matchPattern": f"(?i)^{re.escape(model)}$",
                "unit": "TOKENS",
                "inputPrice": float(in_per_m / _PER_MILLION),
                "outputPrice": float(out_per_m / _PER_MILLION),
            }
            r = c.post("/api/public/models", json=body)
            if r.status_code >= 300:
                print(f"  FAIL {model}: {r.status_code} {r.text[:120]}", file=sys.stderr)
                rc = 1
            else:
                print(f"  ok   {model}: ${in_per_m}/1M in, ${out_per_m}/1M out")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
