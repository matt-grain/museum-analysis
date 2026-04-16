"""Unit tests for CityQueryService."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.city_repository import CityRepository
from museums.repositories.population_record_repository import PopulationRecordRepository
from museums.services.city_query_service import CityQueryService
from tests.factories import build_city, build_population_record


@pytest.mark.asyncio
async def test_list_with_populations_groups_by_city(db_session: AsyncSession) -> None:
    # Arrange
    city1 = await build_city(db_session, qid="QCQ01", name="Paris")
    city2 = await build_city(db_session, qid="QCQ02", name="London")
    await build_population_record(db_session, city=city1, year=2020, population=2_000_000)
    await build_population_record(db_session, city=city1, year=2021, population=2_100_000)
    await build_population_record(db_session, city=city2, year=2020, population=8_000_000)
    await build_population_record(db_session, city=city2, year=2021, population=8_100_000)

    service = CityQueryService(
        city_repo=CityRepository(db_session),
        population_repo=PopulationRecordRepository(db_session),
    )

    # Act
    result = await service.list_with_populations()

    # Assert
    assert len(result) == 2
    by_name = {r.name: r for r in result}
    assert len(by_name["Paris"].population_history) == 2
    assert len(by_name["London"].population_history) == 2


@pytest.mark.asyncio
async def test_list_with_populations_returns_empty_history_for_city_without_records(
    db_session: AsyncSession,
) -> None:
    # Arrange
    await build_city(db_session, qid="QCQ99", name="Empty City")

    service = CityQueryService(
        city_repo=CityRepository(db_session),
        population_repo=PopulationRecordRepository(db_session),
    )

    # Act
    result = await service.list_with_populations()

    # Assert
    assert len(result) == 1
    assert result[0].name == "Empty City"
    assert result[0].population_history == []
