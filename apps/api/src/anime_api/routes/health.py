"""Health + readiness endpoints.

Liveness vs readiness (the K8s distinction, used by the Kubernetes probes):
  - /health  (liveness):  is the process up? No dependencies. Restart pod if this fails.
  - /ready   (readiness): can it actually serve? Checks the DB. Pull from the load
                          balancer if this fails, but DON'T restart — the dep may recover.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from anime_api.dependencies import verify_db_ready
from anime_api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
async def ready(_: None = Depends(verify_db_ready)) -> HealthResponse:
    return HealthResponse(status="ready")
