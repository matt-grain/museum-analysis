"""Tests for HarmonizationService."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.museum_repository import MuseumRepository
from museums.repositories.population_record_repository import PopulationRecordRepository
from museums.repositories.visitor_record_repository import VisitorRecordRepository
from museums.services.harmonization_service import HarmonizationService
from tests.factories import build_city, build_museum, build_population_record, build_visitor_record


def _make_service(session: AsyncSession) -> HarmonizationService:
    return HarmonizationService(
        museum_repo=MuseumRepository(session),
        visitor_repo=VisitorRecordRepository(session),
        population_repo=PopulationRecordRepository(session),
    )


@pytest.mark.asyncio
async def test_build_harmonized_rows_fits_per_city_and_matches_museum_year(
    db_session: AsyncSession,
) -> None:
    # Arrange — city with slope 20_000/year; museum visitor record at 2023
    city = await build_city(db_session, qid="Q1", name="CityA")
    await build_population_record(db_session, city=city, year=2015, population=2_000_000)
    await build_population_record(db_session, city=city, year=2020, population=2_100_000)
    museum = await build_museum(db_session, name="MuseumA", city=city)
    await build_visitor_record(db_session, museum=museum, year=2023, visitors=500_000)

    # Act
    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    # Assert — OLS fit: slope = (2_100_000 - 2_000_000)/(2020 - 2015) = 20_000/yr
    # pop_est at 2023 = 2_000_000 + 20_000 * (2023 - 2015) = 2_160_000
    assert len(rows) == 1
    assert abs(rows[0].population_est - 2_160_000) < 1_000
    assert rows[0].population_is_extrapolated is True  # 2023 > max_year 2020


@pytest.mark.asyncio
async def test_build_harmonized_rows_uses_single_point_fallback_within_2y(
    db_session: AsyncSession,
) -> None:
    # Arrange — only 1 population record; visitor year within ±2y
    city = await build_city(db_session, qid="Q2", name="CityB")
    await build_population_record(db_session, city=city, year=2021, population=3_000_000)
    museum = await build_museum(db_session, name="MuseumB", city=city)
    await build_visitor_record(db_session, museum=museum, year=2023, visitors=300_000)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert len(rows) == 1
    assert rows[0].population_est == 3_000_000
    assert rows[0].population_is_extrapolated is True
    assert rows[0].population_fit_slope is None


@pytest.mark.asyncio
async def test_build_harmonized_rows_skips_single_point_when_far(
    db_session: AsyncSession,
) -> None:
    # Arrange — visitor year=2010, population record year=2021; gap > 2 years
    city = await build_city(db_session, qid="Q3", name="CityC")
    await build_population_record(db_session, city=city, year=2021, population=1_500_000)
    museum = await build_museum(db_session, name="MuseumC", city=city)
    await build_visitor_record(db_session, museum=museum, year=2010, visitors=200_000)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert rows == []


@pytest.mark.asyncio
async def test_build_harmonized_rows_picks_most_recent_visitor_record(
    db_session: AsyncSession,
) -> None:
    # Arrange — museum with 3 visitor records; expect year=2023 to be picked
    city = await build_city(db_session, qid="Q4", name="CityD")
    await build_population_record(db_session, city=city, year=2019, population=1_000_000)
    await build_population_record(db_session, city=city, year=2023, population=1_100_000)
    museum = await build_museum(db_session, name="MuseumD", city=city)
    await build_visitor_record(db_session, museum=museum, year=2019, visitors=100_000)
    await build_visitor_record(db_session, museum=museum, year=2022, visitors=150_000)
    await build_visitor_record(db_session, museum=museum, year=2023, visitors=120_000)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert len(rows) == 1
    assert rows[0].year == 2023


@pytest.mark.asyncio
async def test_build_harmonized_rows_skips_museum_without_city(
    db_session: AsyncSession,
) -> None:
    # Arrange — museum with no city
    museum = await build_museum(db_session, name="MuseumE", city=None)
    await build_visitor_record(db_session, museum=museum, year=2022, visitors=50_000)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert rows == []


@pytest.mark.asyncio
async def test_build_harmonized_rows_skips_city_with_zero_population_records(
    db_session: AsyncSession,
) -> None:
    # Arrange — museum has city but city has no population data
    city = await build_city(db_session, qid="Q6", name="CityF")
    museum = await build_museum(db_session, name="MuseumF", city=city)
    await build_visitor_record(db_session, museum=museum, year=2022, visitors=80_000)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert rows == []


@pytest.mark.asyncio
async def test_build_harmonized_rows_sorts_by_visitors_descending(
    db_session: AsyncSession,
) -> None:
    # Arrange — 3 museums with a shared city; seed visitors so we can assert ordering
    city = await build_city(db_session, qid="Q7", name="CityG")
    await build_population_record(db_session, city=city, year=2018, population=2_000_000)
    await build_population_record(db_session, city=city, year=2022, population=2_080_000)

    for i, (name, visitors) in enumerate([("MG1", 800_000), ("MG2", 200_000), ("MG3", 500_000)]):
        m = await build_museum(db_session, name=name, city=city, qid=f"QG{i}")
        await build_visitor_record(db_session, museum=m, year=2022, visitors=visitors)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert len(rows) == 3
    assert rows[0].visitors >= rows[1].visitors >= rows[2].visitors


@pytest.mark.asyncio
async def test_build_harmonized_rows_flags_extrapolation_outside_fit_range(
    db_session: AsyncSession,
) -> None:
    # Arrange - fit on 2015-2020; visitor year=2024 (beyond max)
    city = await build_city(db_session, qid="Q8", name="CityH")
    await build_population_record(db_session, city=city, year=2015, population=1_000_000)
    await build_population_record(db_session, city=city, year=2020, population=1_050_000)
    museum = await build_museum(db_session, name="MuseumH", city=city)
    await build_visitor_record(db_session, museum=museum, year=2024, visitors=600_000)

    service = _make_service(db_session)
    rows = await service.build_harmonized_rows()

    assert len(rows) == 1
    assert rows[0].population_is_extrapolated is True
