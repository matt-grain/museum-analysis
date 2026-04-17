"""Harmonized data router."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from museums.dependencies import HarmonizationServiceDep
from museums.schemas.harmonized import PaginatedHarmonizedOut

router = APIRouter(prefix="/harmonized", tags=["harmonized"])


@router.get(
    "",
    response_model=PaginatedHarmonizedOut,
    status_code=status.HTTP_200_OK,
    summary="Harmonized (museum, city, year, visitors, population_est) dataset",
    description=(
        "For each museum with a city + visitor record, computes a per-city OLS fit "
        "of population vs. year and projects the population estimate at the museum's "
        "most-recent visitor year. Museums whose city has fewer than 2 population "
        "data points (and no nearby single-point fallback) are dropped. The "
        "`population_is_extrapolated` flag indicates whether the estimate is "
        "inside or outside the fit range."
    ),
)
async def get_harmonized(
    service: HarmonizationServiceDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedHarmonizedOut:
    """Return paginated harmonized museum/population rows computed on demand."""
    return await service.build_harmonized_paginated(skip=skip, limit=limit)
