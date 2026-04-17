"""Harmonized row response DTO."""

from __future__ import annotations

from pydantic import BaseModel

from museums.schemas.common import PaginationMeta


class HarmonizedRowOut(BaseModel):
    museum_id: int
    museum_name: str
    city_id: int
    city_name: str
    year: int
    visitors: int
    population_est: float
    population_is_extrapolated: bool
    population_fit_slope: float | None
    population_fit_intercept: float | None


class PaginatedHarmonizedOut(BaseModel):
    items: list[HarmonizedRowOut]
    pagination: PaginationMeta
