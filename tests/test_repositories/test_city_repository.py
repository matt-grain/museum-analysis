"""Tests for CityRepository."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.city_repository import CityRepository


@pytest.mark.asyncio
async def test_upsert_by_qid_inserts_new_city(db_session: AsyncSession) -> None:
    # Arrange
    repo = CityRepository(db_session)

    # Act
    city = await repo.upsert_by_qid("Q90", "Paris", "France")

    # Assert
    assert city.id is not None
    assert city.wikidata_qid == "Q90"
    assert city.name == "Paris"
    assert city.country == "France"


@pytest.mark.asyncio
async def test_upsert_by_qid_updates_existing_city(db_session: AsyncSession) -> None:
    # Arrange
    repo = CityRepository(db_session)
    await repo.upsert_by_qid("Q90", "Paris", "France")

    # Act — same QID, different name
    updated = await repo.upsert_by_qid("Q90", "Paris (updated)", "France")

    # Assert — only one row, with latest name
    all_cities = await repo.list_all()
    assert len(all_cities) == 1
    assert updated.name == "Paris (updated)"


@pytest.mark.asyncio
async def test_get_by_qid_returns_none_when_missing(db_session: AsyncSession) -> None:
    # Arrange
    repo = CityRepository(db_session)

    # Act
    result = await repo.get_by_qid("Q_DOES_NOT_EXIST")

    # Assert
    assert result is None
