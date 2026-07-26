"""Account-management endpoints — currently just DELETE for GDPR Art 17.

implements the self-service half of RTBF. The operator-side
back-office path is `scripts/rtbf.py`.

Scope guard: there is NO path parameter. The route deletes ONLY the
calling user's account, derived from the auth token. There is no
mechanism in this endpoint by which user A could delete user B.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from anime_core.clerk import ClerkAPIError, ClerkClient
from anime_core.rtbf import delete_user
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from anime_api.auth import AuthedUser, get_current_user
from anime_api.dependencies import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["account"])


@lru_cache(maxsize=1)
def _build_clerk_client() -> ClerkClient | None:
    """Lazy singleton — read CLERK_SECRET_KEY once at first use."""
    secret = os.environ.get("CLERK_SECRET_KEY", "").strip()
    if not secret:
        logger.warning("CLERK_SECRET_KEY not set — Clerk sync on RTBF disabled")
        return None
    return ClerkClient(secret_key=secret)


def get_clerk_client() -> ClerkClient | None:
    """Dependency provider — None means Clerk sync is disabled (logs a warning)."""
    return _build_clerk_client()


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    user: AuthedUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    clerk: ClerkClient | None = Depends(get_clerk_client),
) -> None:
    """GDPR Article 17 right-to-erasure for the calling user.

    Deletes all user-scoped PII rows (feedback, query_history,
    usage_daily, users) + the Clerk-side identity, in a single
    transactional unit. Inserts a row in `account_deletions` as
    compliance evidence (single row per user, idempotent on re-run).

    Returns 204 No Content on success. After this call returns, the
    bearer token used to authenticate is no longer valid (Clerk-side
    delete).
    """
    try:
        summary = await delete_user(
            session,
            user_id=user.id,
            reason="user-initiated via DELETE /v1/account",
            source="self_service",
            dry_run=False,
            clerk_client=clerk,
        )
    except ClerkAPIError as e:
        # Clerk-side failed — DB untouched. Surface as 502 (upstream provider
        # error) so the client can retry. Operator can also retry via the
        # back-office CLI.
        logger.error("rtbf.clerk_failed user_id=%s err=%s", user.id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Identity provider unavailable; please try again shortly.",
        ) from e

    logger.info(
        "rtbf.self_service.complete user_id=%s rows_deleted=%d audit_inserted=%s",
        user.id,
        summary.total_rows,
        summary.audit_row_inserted,
    )
    # 204 returned implicitly — no body.
