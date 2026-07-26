"""API logging shim — the canonical impl lives in anime_core.observability.

Kept as a thin re-export so existing imports (`from anime_api.logging import
configure_logging`) keep working unchanged. The implementation moved
into the shared package so workers inherit the same structured
JSON + PII redaction + trace-ID binding without duplicating the config.
"""

from __future__ import annotations

from anime_core.observability import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
