"""Unit tests for MuseumQueryService."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.museum_repository import MuseumRepository
from museums.services.museum_query_service import MuseumQueryService
from tests.factories import build_city, build_museum, build_visitor_record


@pytest.mark.asyncio
async def test_list_paginated_returns_paginated_museums_out(db_session: AsyncSession) -> None:
    # Arrange
    city = await build_city(db_session)
    m1 = await build_museum(db_session, name="Louvre", qid="QSQ01", city=city)
    m2 = await build_museum(db_session, name="British Museum", qid="QSQ02", city=city)
    m3 = await build_museum(db_session, name="Smithsonian", qid="QSQ03", city=city)
    await build_visitor_record(db_session, museum=m1)
    await build_visitor_record(db_session, museum=m2)
    await build_visitor_record(db_session, museum=m3)

    service = MuseumQueryService(museum_repo=MuseumRepository(db_session))

    # Act
    result = await service.list_paginated(skip=0, limit=10)

    # Assert
    assert len(result.items) == 3
    assert result.pagination.total == 3
    assert result.pagination.skip == 0
    assert result.pagination.limit == 10


@pytest.mark.asyncio
async def test_list_paginated_empty_returns_zero_total(db_session: AsyncSession) -> None:
    # Arrange
    service = MuseumQueryService(museum_repo=MuseumRepository(db_session))

    # Act
    result = await service.list_paginated(skip=0, limit=10)

    # Assert
    assert result.items == []
    assert result.pagination.total == 0
