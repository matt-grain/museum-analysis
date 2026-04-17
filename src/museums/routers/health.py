"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter, status

from museums.dependencies import HealthServiceDep
from museums.schemas.common import HealthOut

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthOut,
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description=(
        "Verifies the database connection by executing a SELECT 1. "
        "Returns 200 when reachable, 503 when the DB is unavailable."
    ),
    responses={503: {"description": "Database is unreachable"}},
)
async def health(service: HealthServiceDep) -> HealthOut:
    """Return 200 OK when the database is reachable."""
    await service.check()
    return HealthOut(status="ok")
