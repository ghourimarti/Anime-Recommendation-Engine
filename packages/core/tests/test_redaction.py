"""Unit tests for the PII redactor."""

from __future__ import annotations

from anime_core.observability.redaction import (
    DENY_KEYS,
    REDACTED,
    redact,
    redact_processor,
)


def test_top_level_email_is_masked() -> None:
    out = redact({"event": "signup", "email": "alice@example.com"})
    assert out["email"] == REDACTED
    assert out["event"] == "signup"  # non-denied passes through


def test_query_is_masked() -> None:
    out = redact({"query": "psychological thriller"})
    assert out["query"] == REDACTED


def test_nested_email_is_masked() -> None:
    """The redactor must descend into nested dicts — request bodies aren't flat."""
    out = redact({"user": {"id": "u1", "email": "alice@example.com"}})
    assert out["user"]["email"] == REDACTED
    assert out["user"]["id"] == "u1"


def test_case_insensitive_match() -> None:
    out = redact({"Email": "x@y.com", "EMAIL": "x@y.com", "eMaIl": "x@y.com"})
    assert all(v == REDACTED for v in out.values())


def test_list_of_dicts_is_redacted() -> None:
    out = redact({"events": [{"email": "a"}, {"email": "b"}]})
    assert out["events"][0]["email"] == REDACTED
    assert out["events"][1]["email"] == REDACTED


def test_non_denied_keys_pass_through() -> None:
    """The classic substring-false-positive: `category` must NOT match `ory`."""
    out = redact({"category": "drama", "userid": "u1", "duration_ms": 42})
    assert out == {"category": "drama", "userid": "u1", "duration_ms": 42}


def test_userEmail_substring_is_NOT_matched() -> None:
    """Exact-key only. `userEmail` is NOT in DENY_KEYS by default — and that's
    intentional. When a real "userEmail leaked" incident happens, the fix is to
    add the alias to DENY_KEYS, not to enable substring matching (which would
    false-positive on `category` etc.)."""
    out = redact({"userEmail": "alice@example.com"})
    assert out["userEmail"] == "alice@example.com"  # NOT redacted


def test_non_string_denied_values_are_masked() -> None:
    """An int 'password' (hashed numeric pin) should still be scrubbed."""
    out = redact({"password": 12345})
    assert out["password"] == REDACTED


def test_idempotent() -> None:
    """Running redact twice produces the same output as running it once."""
    once = redact({"email": "x@y.com", "name": "Alice"})
    twice = redact(once)
    assert once == twice


def test_redact_processor_returns_event_dict() -> None:
    """The structlog processor signature — (logger, method_name, event_dict) → event_dict."""
    out = redact_processor(None, "info", {"event": "signup", "email": "x@y.com"})
    assert out["email"] == REDACTED
    assert out["event"] == "signup"


def test_deny_keys_contains_expected_minimum_set() -> None:
    """If someone removes a key from DENY_KEYS, this test breaks loudly — it's a
    policy change that deserves a code review conversation, not a quiet diff."""
    assert "email" in DENY_KEYS
    assert "password" in DENY_KEYS
    assert "authorization" in DENY_KEYS
    assert "query" in DENY_KEYS
