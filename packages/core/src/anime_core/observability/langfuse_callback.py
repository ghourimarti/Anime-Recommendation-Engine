"""Langfuse callback factory — LLM-specific observability layer.

Langfuse complements OTel: OTel covers app-level spans (HTTP, DB, Redis);
Langfuse captures LLM-specific signal (prompt, completion, tokens, cost, model,
prompt version) which OTel doesn't model natively. They share the same trace_id
when the Langfuse callback runs inside an OTel span.

The factory pattern matters:
  - **Single process-wide handler** — buffers and batches; one client per process.
  - **Returns None when env is incomplete** — the app boots without Langfuse.
    A failed observability dep must NEVER fail the request path.
  - **Async client** — flush()/shutdown() called from the lifespan shutdown hook.

Gate G9: the handler is constructed at startup and passed at chain INVOCATION
(via `config={"callbacks": [handler]}`) — NOT baked into the chain at
construction. This keeps the per-request callback list pluggable for future
per-tenant trace destinations.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_HANDLER: Any | None = None
_INITIALISED = False


def _has_required_env() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def get_langfuse_handler() -> Any | None:
    """Return a process-wide Langfuse CallbackHandler, or None if not configured.

    Idempotent: subsequent calls return the same handler. None is a valid +
    expected return — the app must work without Langfuse.
    """
    global _HANDLER, _INITIALISED
    if _INITIALISED:
        return _HANDLER

    if not _has_required_env():
        logger.info("langfuse keys not set; skipping LLM-trace handler")
        _INITIALISED = True
        return None

    try:
        # Inline import — keeps the langfuse dep cost off the happy path when
        # Langfuse isn't configured.
        from langfuse.langchain import CallbackHandler

        _HANDLER = CallbackHandler()
    except Exception:  # pragma: no cover — defensive: don't break boot on Langfuse import bugs
        logger.warning("langfuse handler init failed; LLM tracing disabled", exc_info=True)
        _HANDLER = None

    _INITIALISED = True
    return _HANDLER


def shutdown_langfuse() -> None:
    """Flush + close the handler — called from the FastAPI lifespan shutdown hook.

    Without this, the last few in-flight traces in the buffer never reach
    Langfuse on dev shutdown. (Looks like "Langfuse isn't working" but it's
    just buffer drop.)
    """
    global _HANDLER
    if _HANDLER is None:
        return
    try:
        # langfuse v3 client exposes flush()/shutdown() on the underlying client.
        # The CallbackHandler proxies, so we try the common method names.
        client = getattr(_HANDLER, "client", None) or getattr(_HANDLER, "langfuse", None)
        if client is None:
            return
        flush = getattr(client, "flush", None)
        if flush is not None:
            flush()
        shutdown = getattr(client, "shutdown", None)
        if shutdown is not None:
            shutdown()
    except Exception:
        logger.warning("langfuse shutdown failed", exc_info=True)


def reset_for_tests() -> None:
    """Test-only: clear the cached handler + init flag so env changes take effect."""
    global _HANDLER, _INITIALISED
    _HANDLER = None
    _INITIALISED = False
