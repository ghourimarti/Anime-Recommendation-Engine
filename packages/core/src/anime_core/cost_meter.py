"""CostMeter — pure pricing math for the per-tenant cost meter.

This module knows three things:
  1. The price-per-million-tokens of every model we call.
  2. How to convert (model, input_tokens, output_tokens) → cost in USD.
  3. The ContextVar that carries the last LLM call's usage from the LLMClient
     up to the FastAPI route, so the route can persist the cost without the
     LLMClient knowing about the request lifecycle.

All money is `decimal.Decimal` end-to-end. Float would accumulate rounding drift
across millions of small per-request increments — a bug that's invisible until
you reconcile against the provider invoice. Use Decimal everywhere money lives.

Prices are NOT hardcoded here. They live in one place — the LLM_PRICING env var —
so a provider rate change is a config edit and a restart, not a code change, a
rebuild and a deploy. Rates move often enough that a table baked into an image
goes stale silently, and stale rates mean you bill against numbers that don't
reconcile with the invoice. The same env var is the source of truth for the
Langfuse model prices (see scripts/langfuse_models.py), so the two can't drift.

Unknown models raise — silent 0-cost recording is the WORST failure mode, because
the cost still gets incurred, it just leaks unattributed.
"""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache


@dataclass(frozen=True)
class TokenUsage:
    """One LLM call's usage record. Emitted by BudgetedLLMClient, consumed by
    the route's cost recording."""

    model: str
    input_tokens: int
    output_tokens: int


_MILLION = Decimal("1000000")

# The env var holding every model's per-million-token price, as JSON:
#   {"<model>": [<input $/1M>, <output $/1M>], ...}
# Rates are given as STRINGS ("0.075", not 0.075): a JSON float is a binary
# double and cannot represent 0.075 exactly, so parsing it would bake a rounding
# error into every cost row before the math even starts.
PRICING_ENV_VAR = "LLM_PRICING"


class UnknownModelError(KeyError):
    """A model with no pricing entry. Silent 0-cost is the WORST failure mode —
    cost leaks unattributed. Fail loud so the operator adds the model to LLM_PRICING."""


class PricingConfigError(ValueError):
    """LLM_PRICING is missing or malformed. Refuse to run rather than meter at $0."""


def parse_pricing(raw: str) -> dict[str, tuple[Decimal, Decimal]]:
    """Parse the LLM_PRICING JSON into a Decimal price table. Raises on anything odd."""
    if not raw.strip():
        raise PricingConfigError(
            f"{PRICING_ENV_VAR} is empty — every LLM call would meter at $0.00 and "
            f"cost would leak unattributed. Set it (see .env.example)."
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PricingConfigError(f"{PRICING_ENV_VAR} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise PricingConfigError(f"{PRICING_ENV_VAR} must be a non-empty JSON object")

    table: dict[str, tuple[Decimal, Decimal]] = {}
    for model, rates in data.items():
        if not isinstance(rates, list | tuple) or len(rates) != 2:
            raise PricingConfigError(
                f"{PRICING_ENV_VAR}[{model!r}] must be [input_per_1m, output_per_1m]"
            )
        try:
            # str() first: tolerate a JSON number, but route it through Decimal's
            # string constructor so we never inherit float's binary rounding.
            in_rate, out_rate = (Decimal(str(r)) for r in rates)
        except InvalidOperation as exc:
            raise PricingConfigError(
                f"{PRICING_ENV_VAR}[{model!r}] has a non-numeric rate"
            ) from exc
        if in_rate < 0 or out_rate < 0:
            raise PricingConfigError(f"{PRICING_ENV_VAR}[{model!r}] has a negative rate")
        table[model] = (in_rate, out_rate)
    return table


@lru_cache(maxsize=1)
def get_pricing() -> dict[str, tuple[Decimal, Decimal]]:
    """The process-wide price table, read once from LLM_PRICING.

    Lazy (not import-time) so importing anime_core never explodes; the first
    actual cost calculation is what forces the config to be present and valid.
    """
    return parse_pricing(os.environ.get(PRICING_ENV_VAR, ""))


class CostMeter:
    """Pure-function cost calculator. No IO, no side effects."""

    def __init__(self, pricing: dict[str, tuple[Decimal, Decimal]] | None = None) -> None:
        # Tests inject their own table; production reads LLM_PRICING.
        self._pricing = pricing if pricing is not None else get_pricing()

    def cost_for(self, *, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        """Return the USD cost of one call. Raises on unknown models."""
        if model not in self._pricing:
            raise UnknownModelError(
                f"no pricing entry for model={model!r}; add it to the {PRICING_ENV_VAR} env var"
            )
        in_rate, out_rate = self._pricing[model]
        return (Decimal(input_tokens) * in_rate + Decimal(output_tokens) * out_rate) / _MILLION

    @property
    def known_models(self) -> list[str]:
        return sorted(self._pricing)


# Carries the last LLM call's usage from BudgetedLLMClient → FastAPI route.
# ContextVar is the right vehicle: per-asyncio-task scope, so concurrent
# requests don't interfere with each other's usage. None means "not yet set
# for this request" (e.g. when the kill switch short-circuited the LLM).
LAST_USAGE: ContextVar[TokenUsage | None] = ContextVar("last_llm_usage", default=None)
