"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy.sql import text

from museums.dependencies import SessionDep
from museums.schemas.common import HealthOut

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthOut, status_code=status.HTTP_200_OK)
async def health(session: SessionDep) -> HealthOut:
    """Return 200 OK when the database is reachable."""
    await session.execute(text("SELECT 1"))
    return HealthOut(status="ok")
