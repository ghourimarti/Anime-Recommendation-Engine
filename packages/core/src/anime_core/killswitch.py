"""LLM_ENABLED, flippable while the process is running.

The switch already existed and worked, with one problem that only shows up when you
need it: `LLM_ENABLED` is read from `os.environ` at call time, and nothing writes to
os.environ at runtime. Turning generation off therefore meant editing `.env` and
restarting the container -- during the cost incident, while it is still spending.

So the value now comes from Redis first and the environment second:

    redis `killswitch:llm` = "off"  -> disabled, immediately, every process
    redis key absent               -> whatever LLM_ENABLED says
    redis unreachable              -> whatever LLM_ENABLED says

That last line is the important one. A cache blip must not disable the product, and
it must not silently ENABLE a product someone deliberately switched off -- so both
failure paths fall back to the environment, which is the same answer the code gave
before this module existed. The switch can only ever be as available as Redis, and
when Redis is gone it degrades to exactly the old behaviour rather than to a guess.

Flip it with `make llm-off` / `make llm-on`, which are two `redis-cli` calls and need
no deploy.
"""

from __future__ import annotations

import logging
import os

from anime_core.cache import Cache

logger = logging.getLogger(__name__)

KILL_SWITCH_KEY = "killswitch:llm"

# No TTL on purpose. An expiring kill switch turns itself back on, which during an
# incident is the one behaviour nobody wants: spend resumes at an arbitrary moment,
# usually unattended, and the graph looks like the fix stopped working.
_OFF_VALUES = frozenset({"off", "false", "0", "disabled"})


def llm_enabled_from_env() -> bool:
    """The environment's answer, which is also the fallback when Redis cannot answer."""
    return os.environ.get("LLM_ENABLED", "true").strip().lower() != "false"


class LlmKillSwitch:
    """Reads the switch. One Redis GET per request, on a connection already in use."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def llm_enabled(self) -> bool:
        try:
            value = await self._cache.get(KILL_SWITCH_KEY)
        except Exception as exc:  # never let the switch itself break the request path
            logger.warning("kill switch unreadable (%s); falling back to LLM_ENABLED", exc)
            return llm_enabled_from_env()
        if value is None:
            return llm_enabled_from_env()
        return value.strip().lower() not in _OFF_VALUES
