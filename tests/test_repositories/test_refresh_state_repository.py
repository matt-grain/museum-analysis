"""Tests for RefreshStateRepository."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.refresh_state_repository import RefreshStateRepository


@pytest.mark.asyncio
async def test_get_auto_creates_singleton_on_empty_table(
    db_session: AsyncSession,
) -> None:
    # Arrange — fresh DB session (rollback isolation guarantees no prior row)
    repo = RefreshStateRepository(db_session)

    # Act
    state = await repo.get()

    # Assert
    assert state.id == 1
    assert state.last_refresh_at is None


@pytest.mark.asyncio
async def test_mark_refreshed_updates_timestamp_and_counts(
    db_session: AsyncSession,
) -> None:
    # Arrange — ensure the singleton row exists first
    repo = RefreshStateRepository(db_session)
    await repo.get()

    # Act
    updated = await repo.mark_refreshed(museums=70, cities=65)

    # Assert
    assert updated.last_refresh_at is not None
    assert updated.last_refresh_museums_count == 70
    assert updated.last_refresh_cities_count == 65
