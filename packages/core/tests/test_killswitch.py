"""The cost kill switch, and specifically its failure directions.

A switch you cannot throw during an incident is not a switch, and a switch that
throws ITSELF during a cache blip is worse than none.
"""

from __future__ import annotations

import pytest
from anime_core.killswitch import KILL_SWITCH_KEY, LlmKillSwitch


class FakeCache:
    def __init__(self, value: str | None = None, *, raises: bool = False) -> None:
        self._value = value
        self._raises = raises
        self.reads = 0

    async def get(self, key: str) -> str | None:
        self.reads += 1
        if self._raises:
            raise ConnectionError("redis is gone")
        return self._value if key == KILL_SWITCH_KEY else None


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["off", "OFF", "false", "0", "disabled"])
async def test_redis_value_disables_generation(value: str) -> None:
    """Every spelling an operator might reach for under pressure."""
    assert await LlmKillSwitch(FakeCache(value)).llm_enabled() is False


@pytest.mark.asyncio
async def test_redis_value_can_re_enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")
    assert await LlmKillSwitch(FakeCache("on")).llm_enabled() is True


@pytest.mark.asyncio
async def test_absent_key_defers_to_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key set is the normal state — the switch must be invisible until thrown."""
    monkeypatch.setenv("LLM_ENABLED", "true")
    assert await LlmKillSwitch(FakeCache(None)).llm_enabled() is True
    monkeypatch.setenv("LLM_ENABLED", "false")
    assert await LlmKillSwitch(FakeCache(None)).llm_enabled() is False


@pytest.mark.asyncio
async def test_unreachable_redis_falls_back_to_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both directions, because both are ways to get this wrong.

    A cache blip must not take generation down (the product would fail on a dependency
    that is only advisory), and it must not turn generation back ON for someone who
    deliberately disabled it in config. Deferring to the environment is the only answer
    that is right in both cases — and it is what the code did before Redis was involved.
    """
    monkeypatch.setenv("LLM_ENABLED", "true")
    assert await LlmKillSwitch(FakeCache(raises=True)).llm_enabled() is True
    monkeypatch.setenv("LLM_ENABLED", "false")
    assert await LlmKillSwitch(FakeCache(raises=True)).llm_enabled() is False


@pytest.mark.asyncio
async def test_switch_is_read_per_call_not_cached() -> None:
    """Throwing it must take effect now, not after some TTL expires."""
    cache = FakeCache("off")
    switch = LlmKillSwitch(cache)
    await switch.llm_enabled()
    await switch.llm_enabled()
    assert cache.reads == 2
