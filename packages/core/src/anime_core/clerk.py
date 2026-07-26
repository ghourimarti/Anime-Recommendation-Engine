"""Thin Clerk Backend API client — used by RTBF for the
auth-identity side of account deletion.

We sync Clerk-side deletion as part of
the RTBF atomic-ish flow. This module is the realization.

Why a hand-rolled client instead of `clerk-backend-api` (the official
Python SDK)? Two reasons:
  1. We need exactly ONE endpoint (DELETE /v1/users/{user_id}). Adding a
     full SDK for one call is mass that has to be maintained.
  2. The SDK pulls a substantial dep tree; our `httpx` is already loaded.

If we ever need more Clerk endpoints (organizations, custom-attributes,
session inspection), revisit and adopt the SDK.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class ClerkAPIError(Exception):
    """Raised on transient or unexpected Clerk API failures (network, 5xx)."""


class ClerkClient:
    """Minimal Clerk Backend API client — DELETE-user only.

    Construction:
        client = ClerkClient(secret_key=os.environ["CLERK_SECRET_KEY"])

    Calls:
        ok = await client.delete_user("user_xxxxx")
        # True on success or "already gone"; raises ClerkAPIError otherwise.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        base_url: str = "https://api.clerk.com/v1",
        timeout: float = 10.0,
    ) -> None:
        if not secret_key:
            raise ValueError("ClerkClient requires a non-empty secret_key")
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def delete_user(self, user_id: str) -> bool:
        """DELETE /v1/users/{user_id}.

        Returns True on success (including the "already gone" 404 case —
        idempotency contract for the RTBF caller). Raises ClerkAPIError on
        anything else.
        """
        url = f"{self._base_url}/users/{user_id}"
        headers = {"Authorization": f"Bearer {self._secret_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.delete(url, headers=headers)
        except httpx.HTTPError as e:
            raise ClerkAPIError(
                f"Clerk delete_user network error: {e.__class__.__name__}: {e}"
            ) from e

        if response.status_code in (200, 204):
            logger.info("clerk.delete_user.ok user_id=%s", user_id)
            return True
        if response.status_code == 404:
            # Idempotency: already gone counts as success.
            logger.info("clerk.delete_user.already_gone user_id=%s", user_id)
            return True
        # 4xx other than 404 is a real client-side problem (bad token, etc.).
        # 5xx is a Clerk-side problem. Both surface as ClerkAPIError so the
        # caller can decide whether to retry or fail the RTBF transaction.
        body = response.text[:300]
        raise ClerkAPIError(f"Clerk delete_user failed: HTTP {response.status_code} body={body!r}")
