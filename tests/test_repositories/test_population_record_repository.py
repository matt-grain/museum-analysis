"""Tests for PopulationRecordRepository."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.population_record_repository import PopulationRecordRepository
from tests.factories import build_city


@pytest.mark.asyncio
async def test_upsert_many_inserts_new_records(db_session: AsyncSession) -> None:
    # Arrange
    city = await build_city(db_session, qid="QPR01", name="Berlin")
    repo = PopulationRecordRepository(db_session)

    # Act
    count = await repo.upsert_many(city.id, [(2019, 3_500_000), (2021, 3_600_000)])

    # Assert
    records = await repo.list_for_city(city.id)
    assert count == 2
    assert len(records) == 2


@pytest.mark.asyncio
async def test_upsert_many_updates_existing_records(db_session: AsyncSession) -> None:
    # Arrange — insert then update with new population value for the same year
    city = await build_city(db_session, qid="QPR02", name="Vienna")
    repo = PopulationRecordRepository(db_session)
    await repo.upsert_many(city.id, [(2020, 1_900_000)])

    # Act — same city_id + year, different population
    await repo.upsert_many(city.id, [(2020, 1_950_000)])

    # Assert — one record, updated population
    records = await repo.list_for_city(city.id)
    assert len(records) == 1
    assert records[0].population == 1_950_000


@pytest.mark.asyncio
async def test_list_all_grouped_returns_dict_keyed_by_city_id(db_session: AsyncSession) -> None:
    # Arrange
    city_a = await build_city(db_session, qid="QPR03", name="Amsterdam")
    city_b = await build_city(db_session, qid="QPR04", name="Brussels")
    repo = PopulationRecordRepository(db_session)
    await repo.upsert_many(city_a.id, [(2018, 800_000), (2020, 820_000)])
    await repo.upsert_many(city_b.id, [(2019, 1_200_000)])

    # Act
    grouped = await repo.list_all_grouped()

    # Assert
    assert city_a.id in grouped
    assert city_b.id in grouped
    assert len(grouped[city_a.id]) == 2
    assert len(grouped[city_b.id]) == 1


@pytest.mark.asyncio
async def test_upsert_many_empty_iterable_returns_zero(db_session: AsyncSession) -> None:
    # Arrange
    city = await build_city(db_session, qid="QPR05", name="Copenhagen")
    repo = PopulationRecordRepository(db_session)

    # Act
    count = await repo.upsert_many(city.id, [])

    # Assert
    assert count == 0
    records = await repo.list_for_city(city.id)
    assert records == []
