"""Unit tests for CostMeter.

Two distinct concerns live here:

1. The arithmetic. These inject an explicit price table so they assert math, not
   config — a test that reads the ambient LLM_PRICING would start failing the day
   a provider changes a rate, which is noise, not signal.

2. The config contract. test_every_configured_model_has_a_price is the one that
   matters: it re-derives, from .env.example, the set of models the app can
   actually call and asserts each has a price. The original bug (every request
   metering at $0.00) was exactly this gap — GROQ_DEFAULT_MODEL was switched to
   openai/gpt-oss-20b and nobody added it to the price table, so cost silently
   went to zero while the provider kept billing. No unit test could see it,
   because the pricing table was internally consistent; only the *cross-check
   against configuration* catches it.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from anime_core.cost_meter import (
    CostMeter,
    PricingConfigError,
    UnknownModelError,
    get_pricing,
    parse_pricing,
)

# Fixed table: these tests assert arithmetic, not today's provider rates.
TABLE = {
    "llama-3.1-8b-instant": (Decimal("0.05"), Decimal("0.08")),
    "llama-3.3-70b-versatile": (Decimal("0.59"), Decimal("0.79")),
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
    "openai/gpt-oss-20b": (Decimal("0.075"), Decimal("0.30")),
}

ENV_EXAMPLE = Path(__file__).resolve().parents[3] / ".env.example"


def _meter() -> CostMeter:
    return CostMeter(TABLE)


def test_groq_8b_cost_uses_pricing_table_rates() -> None:
    # 1_000 * 0.05/1e6 + 500 * 0.08/1e6 = 0.00005 + 0.00004 = 0.00009 USD
    cost = _meter().cost_for(model="llama-3.1-8b-instant", input_tokens=1_000, output_tokens=500)
    assert cost == Decimal("0.00009")


def test_groq_70b_cost_uses_pricing_table_rates() -> None:
    # 2_000 * 0.59/1e6 + 1_000 * 0.79/1e6 = 0.00118 + 0.00079 = 0.00197 USD
    cost = _meter().cost_for(
        model="llama-3.3-70b-versatile", input_tokens=2_000, output_tokens=1_000
    )
    assert cost == Decimal("0.00197")


def test_openai_fallback_cost_uses_pricing_table_rates() -> None:
    # 10_000 * 0.15/1e6 + 2_000 * 0.60/1e6 = 0.0015 + 0.0012 = 0.0027
    cost = _meter().cost_for(model="gpt-4o-mini", input_tokens=10_000, output_tokens=2_000)
    assert cost == Decimal("0.0027")


def test_unknown_model_fails_loud() -> None:
    """Silent 0-cost on an unknown model is the WORST failure mode — the provider
    still bills, the cost just leaks unattributed. Fail loud."""
    with pytest.raises(UnknownModelError):
        _meter().cost_for(model="some-future-model", input_tokens=1, output_tokens=1)


def test_zero_tokens_is_zero_cost_for_every_known_model() -> None:
    meter = _meter()
    for model in TABLE:
        assert meter.cost_for(model=model, input_tokens=0, output_tokens=0) == Decimal("0")


def test_cost_uses_decimal_not_float() -> None:
    """Cost must be Decimal so accumulation across millions of rows doesn't drift."""
    result = _meter().cost_for(model="llama-3.1-8b-instant", input_tokens=1, output_tokens=1)
    assert isinstance(result, Decimal)


def test_custom_pricing_table_overrides_env() -> None:
    meter = CostMeter({"test-model": (Decimal("1.00"), Decimal("2.00"))})
    # 1M * $1/1M + 0.5M * $2/1M = $1 + $1 = $2
    assert meter.cost_for(model="test-model", input_tokens=1_000_000, output_tokens=500_000) == (
        Decimal("2.00")
    )


# ── LLM_PRICING parsing ──────────────────────────────────────────────────────


def test_parse_pricing_reads_string_rates_exactly() -> None:
    table = parse_pricing('{"m": ["0.075", "0.30"]}')
    assert table["m"] == (Decimal("0.075"), Decimal("0.30"))


def test_parse_pricing_keeps_precision_a_float_would_lose() -> None:
    """0.075 is not representable in binary floating point.

    Rates are declared as JSON strings for this reason. If a rate ever arrives as
    a JSON number we still route it through Decimal(str(x)) rather than
    Decimal(float), so we never inherit the binary expansion.
    """
    table = parse_pricing('{"m": ["0.075", "0.30"]}')
    in_rate, _ = table["m"]
    assert in_rate == Decimal("0.075")
    naive_float_rate = 0.075  # what json.loads would hand us for a bare JSON number
    assert in_rate != Decimal(naive_float_rate)  # 0.07500000000000000277...


def test_empty_pricing_config_refuses_to_run() -> None:
    """Empty LLM_PRICING would meter every call at $0. Refuse, don't default."""
    with pytest.raises(PricingConfigError, match="empty"):
        parse_pricing("")


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        "{}",
        '{"m": ["0.1"]}',  # wrong arity
        '{"m": "0.1"}',  # not a pair
        '{"m": ["abc", "0.1"]}',  # non-numeric
        '{"m": ["-0.1", "0.1"]}',  # negative
    ],
)
def test_malformed_pricing_config_raises(raw: str) -> None:
    with pytest.raises(PricingConfigError):
        parse_pricing(raw)


def test_env_pricing_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    get_pricing.cache_clear()
    monkeypatch.setenv("LLM_PRICING", '{"m": ["1", "2"]}')
    assert get_pricing()["m"] == (Decimal("1"), Decimal("2"))
    # Second call must not re-read the env — the table is process-wide.
    monkeypatch.setenv("LLM_PRICING", '{"other": ["9", "9"]}')
    assert "m" in get_pricing()
    get_pricing.cache_clear()


# ── the cross-check that actually catches the bug ────────────────────────────


def _env_example() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        values[k.strip()] = v.strip()
    return values


def test_shipped_env_example_pricing_is_valid() -> None:
    """The LLM_PRICING we ship must actually parse. A typo here meters everything at $0."""
    table = parse_pricing(_env_example()["LLM_PRICING"])
    assert table, "shipped LLM_PRICING parsed to an empty table"


def test_every_configured_model_has_a_price() -> None:
    """Every model the app is configured to CALL must have a price.

    This is the regression guard for the $0.00 cost bug: switching
    GROQ_DEFAULT_MODEL to a model absent from the price table silently zeroed all
    cost accounting. Any *_MODEL setting is a model we will call, so it needs a
    rate — enforced here, at the config level, where the gap actually lives.
    """
    env = _env_example()
    table = parse_pricing(env["LLM_PRICING"])
    configured = {
        key: value
        for key, value in env.items()
        if re.fullmatch(r"(GROQ|OPENAI)_\w*MODEL", key) and value
    }
    assert configured, "no *_MODEL settings found — did the env keys get renamed?"
    missing = {k: v for k, v in configured.items() if v not in table}
    assert not missing, (
        f"models configured but unpriced: {missing}. They would meter at $0.00 while the "
        f"provider still bills. Priced models: {sorted(table)}"
    )


def test_pricing_json_survives_dotenv_roundtrip() -> None:
    """LLM_PRICING is JSON living inside a .env line — commas, colons, braces and
    quotes all intact. Guards against someone 'tidying' it into a broken form."""
    raw = _env_example()["LLM_PRICING"]
    assert raw.startswith("{") and raw.endswith("}")
    assert json.loads(raw)  # parses as-is, unquoted, straight from the file
