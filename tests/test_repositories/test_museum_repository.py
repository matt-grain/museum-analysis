"""Tests for MuseumRepository."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.museum_repository import MuseumRepository
from tests.factories import build_city, build_museum


@pytest.mark.asyncio
async def test_upsert_by_name_inserts_and_then_updates(
    db_session: AsyncSession,
) -> None:
    # Arrange
    repo = MuseumRepository(db_session)

    # Act — first insert
    museum = await repo.upsert_by_name(
        name="Louvre",
        wikipedia_title="Louvre",
        wikidata_qid="Q19675",
        city_id=None,
        country=None,
    )

    # Assert — row created
    assert museum.id is not None
    assert museum.name == "Louvre"

    # Act — update with same name
    updated = await repo.upsert_by_name(
        name="Louvre",
        wikipedia_title="Louvre Museum",
        wikidata_qid="Q19675",
        city_id=None,
        country="France",
    )

    # Assert — same row, updated fields
    assert updated.id == museum.id
    assert updated.wikipedia_title == "Louvre Museum"
    assert updated.country == "France"


@pytest.mark.asyncio
async def test_list_paginated_returns_items_and_total(
    db_session: AsyncSession,
) -> None:
    # Arrange — seed 3 museums
    repo = MuseumRepository(db_session)
    for i in range(3):
        await repo.upsert_by_name(
            name=f"Museum {i}",
            wikipedia_title=f"Museum {i}",
            wikidata_qid=None,
            city_id=None,
            country=None,
        )

    # Act
    items, total = await repo.list_paginated(skip=0, limit=2)

    # Assert
    assert total == 3
    assert len(items) == 2


@pytest.mark.asyncio
async def test_list_paginated_eager_loads_city(db_session: AsyncSession) -> None:
    # Arrange — museum with associated city
    city = await build_city(db_session, qid="Q84", name="London", country="UK")
    museum = await build_museum(
        db_session,
        name="British Museum",
        wikipedia_title="British Museum",
        city=city,
        qid="Q6373",
    )
    repo = MuseumRepository(db_session)

    # Act
    items, _ = await repo.list_paginated(skip=0, limit=10)

    # Assert — city is loaded; accessing .name must not trigger a lazy-load error
    loaded = next(m for m in items if m.id == museum.id)
    unloaded = inspect(loaded).unloaded
    assert "city" not in unloaded, "city relationship should be eagerly loaded"
    assert loaded.city is not None
    assert loaded.city.name == "London"
