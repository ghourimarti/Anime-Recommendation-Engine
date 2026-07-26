"""PII redaction.

Drops sensitive values from structured log records BEFORE they hit the
JSONRenderer. The senior pattern: redact at the structured-data layer (keys are
known), not at the serialized layer (regex on JSON is slow + fragile + leaks
partial matches).

Policy decisions (gates G2/G3/G4 from the build walkthrough):
  - **Deny-list, not allow-list.** Allow-list blocks fields the team adds
    later; deny-list lets us add new sensitive names as we learn them.
  - **Mask with REDACTED, not drop.** Dropping creates ambiguity — was the
    field absent or scrubbed? Masking makes the policy visible in the log.
  - **Exact-key match, case-insensitive.** Substring would false-positive
    (`category` ⊃ `ory`). Add explicit aliases (`user_email`, `client_email`)
    to DENY_KEYS as they appear in real code — never enable substring matching.

The processor is idempotent: running it twice produces the same output.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

REDACTED = "[REDACTED]"

# Exact key names (lower-cased) whose values are scrubbed. Add aliases here as
# new sensitive field names appear in code — DO NOT enable substring matching.
DENY_KEYS: frozenset[str] = frozenset(
    {
        "email",
        "query",
        "password",
        "authorization",
        "api_key",
        "apikey",
        "client_ip",
        "ip",
        "secret",
        "token",
        "access_token",
        "refresh_token",
    }
)


def _is_denied(key: str, denied: Iterable[str]) -> bool:
    """Case-insensitive exact-key match against the deny-list."""
    return key.lower() in denied


def redact(data: Any, denied: Iterable[str] = DENY_KEYS) -> Any:
    """Recursively mask values for keys in the deny-list.

    Handles dict, list, and tuple containers. Scalars (str, int, etc.) pass
    through unchanged when called at the top level — but if their parent key
    matched the deny-list, the parent dict's call already masked them.
    """
    denied_set = frozenset(d.lower() for d in denied)
    return _redact_inner(data, denied_set)


def _redact_inner(data: Any, denied: frozenset[str]) -> Any:
    if isinstance(data, Mapping):
        return {
            key: (REDACTED if _is_denied(str(key), denied) else _redact_inner(value, denied))
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [_redact_inner(item, denied) for item in data]
    if isinstance(data, tuple):
        return tuple(_redact_inner(item, denied) for item in data)
    return data


def redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor — masks deny-listed keys in the event dict.

    Hook this into structlog.configure(processors=[...]) BEFORE the renderer
    (JSON or otherwise) so the serialized output is already scrubbed. Idempotent.
    """
    return _redact_inner(event_dict, DENY_KEYS)  # type: ignore[no-any-return]
