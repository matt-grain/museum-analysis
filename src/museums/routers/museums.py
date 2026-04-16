"""Museums list router."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from museums.dependencies import MuseumQueryServiceDep
from museums.schemas.museum import PaginatedMuseumsOut

router = APIRouter(prefix="/museums", tags=["museums"])


@router.get("", response_model=PaginatedMuseumsOut, status_code=status.HTTP_200_OK)
async def list_museums(
    service: MuseumQueryServiceDep,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> PaginatedMuseumsOut:
    """Return a paginated list of museums."""
    return await service.list_paginated(skip=skip, limit=limit)
