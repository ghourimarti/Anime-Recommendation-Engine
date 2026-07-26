"""Unit tests for the Langfuse callback factory."""

from __future__ import annotations

import pytest
from anime_core.observability.langfuse_callback import (
    get_langfuse_handler,
    reset_for_tests,
)


@pytest.fixture(autouse=True)
def _isolate() -> None:
    reset_for_tests()


def test_returns_none_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app MUST boot without Langfuse keys — a missing observability dep
    can never break the request path."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert get_langfuse_handler() is None


def test_returns_none_when_only_public_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Partial config is still no-config — both keys are needed to send a trace."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert get_langfuse_handler() is None


def test_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two calls return the same instance — handler is a singleton per process."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    first = get_langfuse_handler()
    second = get_langfuse_handler()
    assert first is second  # both None, but same reference
