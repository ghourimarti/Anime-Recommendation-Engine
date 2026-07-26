"""Query-history endpoint — paginated read of past recommendations.

Pagination from day one (limit/offset, capped): an unbounded /history read melts
the DB under load. Anonymous in v1; scoped per user once auth is on.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from anime_api.auth import AuthedUser, get_current_user
from anime_api.config import get_settings
from anime_api.dependencies import get_repository
from anime_api.repository import Repository
from anime_api.schemas import HistoryItem, HistoryResponse, RecommendationOut

router = APIRouter(tags=["history"])


@router.get("/history", response_model=HistoryResponse)
async def list_history(
    user: AuthedUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> HistoryResponse:
    settings = get_settings()
    capped_limit = min(limit, settings.history_max_limit)
    # Scoped to the authenticated user — never returns another user's history.
    rows = await repo.list_query_history(user_id=user.id, limit=capped_limit, offset=offset)
    items = [
        HistoryItem(
            id=row.id,
            query=row.query,
            recommendations=[RecommendationOut(**rec) for rec in row.response.get("items", [])],
            created_at=row.created_at,
        )
        for row in rows
    ]
    return HistoryResponse(items=items, limit=capped_limit, offset=offset)
