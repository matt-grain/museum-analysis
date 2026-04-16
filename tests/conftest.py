"""Shared fixtures for the museums test suite."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from museums.config import Settings
from museums.models import Base

# Test database URL — always points at museums_test, never the main DB.
# Override via MUSEUMS_TEST_DATABASE_URL env var if needed.
_TEST_DB_URL = "postgresql+asyncpg://museums:museums@localhost:5432/museums_test"


@pytest.fixture
def settings() -> Settings:
    """Return a Settings instance with test-friendly overrides."""
    return Settings(
        database_url="postgresql+asyncpg://museums:museums@localhost:5432/museums_test",  # type: ignore[arg-type]
        log_level="DEBUG",
        refresh_cooldown_hours=1,
    )


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio as the anyio backend."""
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def async_engine() -> AsyncGenerator[AsyncEngine]:
    """Session-scoped async engine pointing at museums_test.

    Drops and recreates all tables once at session start so every test
    session starts from a clean schema.
    """
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Function-scoped AsyncSession that rolls back after every test.

    Creates a new transaction per test and rolls back on teardown
    so tests never leak data to one another.
    """
    session_factory = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session, session.begin():
        yield session
        await session.rollback()
