"""Tests for VisitorRecordRepository."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from museums.repositories.visitor_record_repository import VisitorRecordRepository
from tests.factories import build_museum


@pytest.mark.asyncio
async def test_upsert_many_inserts_new_records(db_session: AsyncSession) -> None:
    # Arrange
    museum = await build_museum(db_session, qid="QVR01")
    repo = VisitorRecordRepository(db_session)

    # Act
    count = await repo.upsert_many(museum.id, [(2020, 1_000_000), (2021, 1_100_000)])

    # Assert
    records = await repo.list_for_museum(museum.id)
    assert count == 2
    assert len(records) == 2


@pytest.mark.asyncio
async def test_upsert_many_updates_existing_records(db_session: AsyncSession) -> None:
    # Arrange — insert initial record, then upsert with updated visitor count
    museum = await build_museum(db_session, qid="QVR02")
    repo = VisitorRecordRepository(db_session)
    await repo.upsert_many(museum.id, [(2022, 500_000)])

    # Act — same museum_id + year, different visitors
    await repo.upsert_many(museum.id, [(2022, 750_000)])

    # Assert — only one record, value updated
    records = await repo.list_for_museum(museum.id)
    assert len(records) == 1
    assert records[0].visitors == 750_000


@pytest.mark.asyncio
async def test_list_for_museum_returns_records_ordered_by_year_desc(db_session: AsyncSession) -> None:
    # Arrange
    museum = await build_museum(db_session, qid="QVR03")
    repo = VisitorRecordRepository(db_session)
    await repo.upsert_many(museum.id, [(2021, 900_000), (2023, 1_200_000), (2022, 1_000_000)])

    # Act
    records = await repo.list_for_museum(museum.id)

    # Assert — descending year order
    years = [r.year for r in records]
    assert years == sorted(years, reverse=True)
    assert years[0] == 2023
