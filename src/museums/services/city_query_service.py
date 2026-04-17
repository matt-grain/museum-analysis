"""City query service — thin read-only layer for cities + population history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from museums.schemas.city import CityPopulationsOut, PaginatedCitiesOut, PopulationPointOut
from museums.schemas.common import PaginationMeta

if TYPE_CHECKING:
    from museums.repositories.city_repository import CityRepository
    from museums.repositories.population_record_repository import PopulationRecordRepository


class CityQueryService:
    """Wraps CityRepository + PopulationRecordRepository, returns typed DTOs."""

    def __init__(
        self,
        city_repo: CityRepository,
        population_repo: PopulationRecordRepository,
    ) -> None:
        self._city_repo = city_repo
        self._population_repo = population_repo

    async def list_paginated(self, skip: int, limit: int) -> PaginatedCitiesOut:
        """Return a paginated slice of cities with their population history."""
        cities = await self._city_repo.list_all()
        grouped = await self._population_repo.list_all_grouped()
        sorted_cities = sorted(cities, key=lambda c: c.name)
        total = len(sorted_cities)
        page = sorted_cities[skip : skip + limit]
        items = [
            CityPopulationsOut(
                id=city.id,
                name=city.name,
                wikidata_qid=city.wikidata_qid,
                country=city.country,
                population_history=[PopulationPointOut.model_validate(p) for p in grouped.get(city.id, [])],
            )
            for city in page
        ]
        return PaginatedCitiesOut(items=items, pagination=PaginationMeta(total=total, skip=skip, limit=limit))
