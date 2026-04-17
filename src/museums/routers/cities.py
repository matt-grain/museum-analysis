"""Cities router — city population history."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from museums.dependencies import CityQueryServiceDep
from museums.schemas.city import PaginatedCitiesOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get(
    "/populations",
    response_model=PaginatedCitiesOut,
    status_code=status.HTTP_200_OK,
    summary="List cities with their population time series",
    description=(
        "Returns every city referenced by at least one museum, with its full "
        "population history (Wikidata property P1082, point-in-time qualifier P585). "
        "Values outside the 0.5x-2x range of the series minimum are filtered as "
        "scope-mismatch outliers — see the Harmonization ADR in decisions.md."
    ),
)
async def list_city_populations(
    service: CityQueryServiceDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedCitiesOut:
    """Return paginated cities with their full population history."""
    return await service.list_paginated(skip=skip, limit=limit)
