"""Workflow test fixtures — session without outer transaction (workflow owns commit)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest_asyncio.fixture
async def workflow_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Function-scoped AsyncSession without a wrapping transaction.

    Workflow tests need this because IngestionWorkflow calls session.commit()
    and session.rollback() directly — the workflow owns the transaction boundary.
    Each test truncates relevant tables in teardown to keep test isolation.
    """
    session_factory = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        yield session
        # Cleanup: wipe ingestion data between tests
        from sqlalchemy import text

        await session.execute(
            text(
                "TRUNCATE museums, cities, visitor_records, population_records, refresh_state RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
