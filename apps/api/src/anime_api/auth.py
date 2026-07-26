"""Clerk JWT authentication — the request gate.

Verifies a Bearer RS256 token against Clerk's JWKS, checking signature + expiry
(+ issuer/audience when configured). Fails CLOSED: missing/invalid token → 401,
unconfigured auth → 503. The verified `sub` claim is the user id — identity comes
ONLY from the token, never from the request body (no IDOR).

Verification runs in a thread (PyJWKClient is sync and fetches/caches the JWKS on
first use) so it never blocks the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from anime_api.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AuthedUser(BaseModel):
    """The authenticated identity extracted from a verified Clerk JWT."""

    id: str
    email: str | None = None


@lru_cache
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    """Cached JWKS client (caches signing keys across requests)."""
    return jwt.PyJWKClient(jwks_url)


def _verify_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify signature + claims; return the decoded payload. Sync (run via to_thread)."""
    signing_key = _jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.clerk_audience or None,
        issuer=settings.clerk_issuer or None,
        # leeway absorbs clock skew between Clerk's signing servers and this pod;
        # without it a trailing clock 401s valid tokens on "iat"/"nbf". It widens
        # the exp window by the same amount, which is the accepted trade.
        leeway=timedelta(seconds=settings.jwt_leeway_seconds),
        options={"require": ["exp", "sub"], "verify_aud": bool(settings.clerk_audience)},
    )


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    return header[7:].strip() or None


async def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthedUser:
    """Require a valid Clerk JWT. 401 if missing/invalid, 503 if auth unconfigured."""
    token = _bearer_token(request)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or malformed bearer token")
    if not settings.clerk_jwks_url:
        # Fail closed rather than silently accept when auth isn't configured.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "authentication not configured")
    try:
        claims = await asyncio.to_thread(_verify_token, token, settings)
    except jwt.PyJWTError as exc:
        logger.info("rejected token: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing subject")
    return AuthedUser(id=str(sub), email=claims.get("email"))


async def get_optional_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthedUser | None:
    """Like get_current_user but returns None instead of 401 when no token is present."""
    if _bearer_token(request) is None:
        return None
    return await get_current_user(request, settings)
