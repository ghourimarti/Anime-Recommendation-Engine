"""Tests for the static popular fallback."""

from __future__ import annotations

from anime_core.fallback import DEGRADED_NOTICE, NO_MATCH_NOTICE, popular_fallback


def test_popular_fallback_is_degraded_and_non_empty() -> None:
    result = popular_fallback()
    assert result.degraded is True
    assert not result.is_empty
    assert result.notice == DEGRADED_NOTICE
    # real corpus mal_ids so source links resolve
    assert all(r.mal_id > 0 for r in result.items)


def test_popular_fallback_custom_notice() -> None:
    result = popular_fallback(NO_MATCH_NOTICE)
    assert result.notice == NO_MATCH_NOTICE
    assert result.degraded is True
