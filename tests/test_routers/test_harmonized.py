"""Integration tests for GET /harmonized."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import build_city, build_museum, build_population_record, build_visitor_record


@pytest.mark.asyncio
async def test_get_harmonized_returns_rows_when_data_present(
    seeding_session: AsyncSession, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    city = await build_city(seeding_session, qid="QH90", name="Paris")
    museum = await build_museum(seeding_session, name="Louvre", wikipedia_title="Louvre", qid="QH675", city=city)
    await build_visitor_record(seeding_session, museum=museum, year=2022, visitors=7_000_000)
    # Two population records so OLS fit works
    await build_population_record(seeding_session, city=city, year=2021, population=2_100_000)
    await build_population_record(seeding_session, city=city, year=2023, population=2_150_000)
    await seeding_session.commit()

    # Act
    response = await app_client.get("/harmonized")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["museum_name"] == "Louvre"
    assert body["items"][0]["city_name"] == "Paris"


@pytest.mark.asyncio
async def test_get_harmonized_returns_empty_items_when_no_data(app_client: httpx.AsyncClient) -> None:
    # Act
    response = await app_client.get("/harmonized")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["pagination"]["total"] == 0
