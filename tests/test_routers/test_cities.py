"""Integration tests for GET /cities/populations."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import build_city, build_population_record


@pytest.mark.asyncio
async def test_list_city_populations_returns_series_per_city(
    seeding_session: AsyncSession, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    city1 = await build_city(seeding_session, qid="QRC01", name="Paris")
    city2 = await build_city(seeding_session, qid="QRC02", name="London")
    await build_population_record(seeding_session, city=city1, year=2020, population=2_000_000)
    await build_population_record(seeding_session, city=city1, year=2021, population=2_100_000)
    await build_population_record(seeding_session, city=city1, year=2022, population=2_150_000)
    await build_population_record(seeding_session, city=city2, year=2020, population=8_000_000)
    await build_population_record(seeding_session, city=city2, year=2021, population=8_100_000)
    await build_population_record(seeding_session, city=city2, year=2022, population=8_200_000)
    await seeding_session.commit()

    # Act
    response = await app_client.get("/cities/populations")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 2
    by_name = {c["name"]: c for c in body["items"]}
    assert len(by_name["Paris"]["population_history"]) == 3
    assert len(by_name["London"]["population_history"]) == 3
