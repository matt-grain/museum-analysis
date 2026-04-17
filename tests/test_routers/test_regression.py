"""Integration tests for GET /regression."""

from __future__ import annotations

import math

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import build_city, build_museum, build_population_record, build_visitor_record

# 6 museum/city pairs with an approximate log-linear relationship.
# Each tuple is (museum_name, city_name, city_qid, museum_qid, population, visitors).
# Using a flat tuple list rather than factory calls here because the data drives
# a deterministic mathematical invariant (log-linear R²) — the exact values matter
# and wrapping them in factory calls would obscure the relationship without simplifying the test.
_MUSEUM_DATA = [
    ("Museum A", "City A", "QC01", "QM01", 5_000_000, 2_000_000),
    ("Museum B", "City B", "QC02", "QM02", 8_000_000, 3_500_000),
    ("Museum C", "City C", "QC03", "QM03", 12_000_000, 5_000_000),
    ("Museum D", "City D", "QC04", "QM04", 18_000_000, 7_500_000),
    ("Museum E", "City E", "QC05", "QM05", 25_000_000, 9_000_000),
    ("Museum F", "City F", "QC06", "QM06", 30_000_000, 10_000_000),
]


@pytest.mark.asyncio
async def test_get_regression_returns_fit_when_enough_data(
    seeding_session: AsyncSession, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    for museum_name, city_name, city_qid, museum_qid, population, visitors in _MUSEUM_DATA:
        city = await build_city(seeding_session, qid=city_qid, name=city_name)
        museum = await build_museum(
            seeding_session,
            name=museum_name,
            wikipedia_title=museum_name,
            city=city,
            qid=museum_qid,
        )
        await build_visitor_record(seeding_session, museum=museum, year=2022, visitors=visitors)
        await build_population_record(seeding_session, city=city, year=2021, population=population)
        await build_population_record(seeding_session, city=city, year=2023, population=population + 100_000)
    await seeding_session.commit()

    # Act
    response = await app_client.get("/regression")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert "coefficient" in body
    assert "r_squared" in body
    assert body["n_samples"] == 6
    assert math.isfinite(body["coefficient"])


@pytest.mark.asyncio
async def test_get_regression_returns_422_when_insufficient_data(
    app_client: httpx.AsyncClient,
) -> None:
    # Act (no data seeded — 0 harmonized rows < 5 minimum)
    response = await app_client.get("/regression")

    # Assert
    assert response.status_code == 422
    assert response.json()["code"] == "insufficient_data"
