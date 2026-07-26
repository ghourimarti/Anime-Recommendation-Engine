"""Tests for Clerk JWT verification — real RS256 keypair, mocked JWKS (offline)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt
import pytest
from anime_api import auth as auth_mod
from anime_api.config import Settings
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from starlette.requests import Request


@pytest.fixture
def keypair() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def _settings() -> Settings:
    return Settings(clerk_jwks_url="https://example.test/jwks", clerk_issuer="", clerk_audience="")


def _request(authorization: str | None) -> Request:
    headers = [(b"authorization", authorization.encode())] if authorization else []
    return Request({"type": "http", "headers": headers})


def _patch_jwks(monkeypatch: pytest.MonkeyPatch, public_pem: bytes) -> None:
    monkeypatch.setattr(
        auth_mod,
        "_jwks_client",
        lambda url: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_pem)
        ),
    )


@pytest.mark.asyncio
async def test_valid_token_accepted(monkeypatch: pytest.MonkeyPatch, keypair) -> None:  # type: ignore[no-untyped-def]
    private_pem, public_pem = keypair
    _patch_jwks(monkeypatch, public_pem)
    token = jwt.encode(
        {"sub": "user_123", "email": "a@b.com", "exp": int(time.time()) + 3600},
        private_pem,
        algorithm="RS256",
    )
    user = await auth_mod.get_current_user(_request(f"Bearer {token}"), _settings())
    assert user.id == "user_123"
    assert user.email == "a@b.com"


@pytest.mark.asyncio
async def test_missing_token_401() -> None:
    with pytest.raises(HTTPException) as exc:
        await auth_mod.get_current_user(_request(None), _settings())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_401(monkeypatch: pytest.MonkeyPatch, keypair) -> None:  # type: ignore[no-untyped-def]
    private_pem, public_pem = keypair
    _patch_jwks(monkeypatch, public_pem)
    token = jwt.encode(
        # Expired well past jwt_leeway_seconds. (Inside the leeway window an
        # expired token IS still accepted — that is the documented cost of skew
        # tolerance; see test_expiry_grace_is_bounded_by_leeway.)
        {"sub": "user_123", "exp": int(time.time()) - 3600},
        private_pem,
        algorithm="RS256",
    )
    with pytest.raises(HTTPException) as exc:
        await auth_mod.get_current_user(_request(f"Bearer {token}"), _settings())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_tampered_token_401(monkeypatch: pytest.MonkeyPatch, keypair) -> None:  # type: ignore[no-untyped-def]
    private_pem, public_pem = keypair
    _patch_jwks(monkeypatch, public_pem)
    token = jwt.encode({"sub": "u", "exp": int(time.time()) + 3600}, private_pem, algorithm="RS256")
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    with pytest.raises(HTTPException) as exc:
        await auth_mod.get_current_user(_request(f"Bearer {tampered}"), _settings())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_unconfigured_auth_fails_closed(keypair) -> None:  # type: ignore[no-untyped-def]
    # No jwks_url configured → must 503, never silently accept.
    settings = Settings(clerk_jwks_url="", clerk_issuer="", clerk_audience="")
    with pytest.raises(HTTPException) as exc:
        await auth_mod.get_current_user(_request("Bearer whatever"), settings)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_clock_skew_token_accepted(monkeypatch: pytest.MonkeyPatch, keypair) -> None:  # type: ignore[no-untyped-def]
    """A token issued a few seconds 'in the future' must still verify.

    Regression: jwt.decode ran with no leeway, so a pod whose clock trailed
    Clerk's signing servers rejected freshly-minted tokens with
    "The token is not yet valid (iat)" — intermittent 401s for real users.
    """
    private_pem, public_pem = keypair
    _patch_jwks(monkeypatch, public_pem)
    now = int(time.time())
    token = jwt.encode(
        {"sub": "user_skew", "iat": now + 10, "nbf": now + 10, "exp": now + 3600},
        private_pem,
        algorithm="RS256",
    )
    user = await auth_mod.get_current_user(_request(f"Bearer {token}"), _settings())
    assert user.id == "user_skew"


@pytest.mark.asyncio
async def test_expiry_grace_is_bounded_by_leeway(monkeypatch: pytest.MonkeyPatch, keypair) -> None:  # type: ignore[no-untyped-def]
    """Pins the cost of skew tolerance: leeway widens `exp` as well as `iat`/`nbf`.

    RFC 7519 §4.1.4 sanctions "some small leeway" on time claims, and PyJWT (like
    every JWT library) applies one leeway to all of them — you cannot buy iat
    tolerance without granting the same grace on exp. So a token expired by less
    than jwt_leeway_seconds still verifies. That is deliberate and bounded; this
    test exists so the window can never be widened silently.
    """
    private_pem, public_pem = keypair
    _patch_jwks(monkeypatch, public_pem)
    settings = _settings()
    just_expired = int(time.time()) - (settings.jwt_leeway_seconds - 10)
    token = jwt.encode({"sub": "u_grace", "exp": just_expired}, private_pem, algorithm="RS256")
    user = await auth_mod.get_current_user(_request(f"Bearer {token}"), settings)
    assert user.id == "u_grace"
