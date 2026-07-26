"""API configuration — one typed Settings object, read from env once (12-factor).

Centralizes the API's own config. The DB engine and LLM client read their own
env vars where they live (DATABASE_URL, GROQ_API_KEY, ...); this object holds
the HTTP-layer knobs so routes never touch os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """HTTP-layer configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]
    history_default_limit: int = 20
    history_max_limit: int = 100

    # Clerk auth. jwks_url verifies RS256 token signatures; issuer/audience
    # are checked when set. Empty jwks_url → auth fails closed (503), so a
    # misconfigured deploy denies rather than silently accepts.
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_audience: str = ""
    # Clock-skew tolerance for JWT time claims (iat/nbf/exp). Without it, a pod
    # whose clock trails Clerk's signing servers by even a second rejects
    # freshly-minted tokens with "not yet valid (iat)" — an intermittent 401 for
    # legitimate users at sign-in. 60s is the conventional allowance.
    jwt_leeway_seconds: int = 60

    # Quota + cost controls. The free-tier daily cap is the
    # number of /v1/recommend* calls a single user may make per UTC day. Over →
    # HTTP 429 with Retry-After seconds-until-midnight.
    quota_free_tier_daily: int = 20


@lru_cache
def get_settings() -> Settings:
    """Process-wide cached settings."""
    return Settings()
