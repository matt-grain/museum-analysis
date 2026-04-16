"""Shared fixtures for the museums test suite."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from museums.config import Settings
from museums.models import Base

# Test database URL — always points at museums_test, never the main DB.
# Override via MUSEUMS_TEST_DATABASE_URL env var if needed.
_TEST_DB_URL = "postgresql+asyncpg://museums:museums@localhost:5432/museums_test"

_TRUNCATE_SQL = text(
    "TRUNCATE museums, cities, visitor_records, population_records, refresh_state RESTART IDENTITY CASCADE"
)


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
    """Session-scoped async engine pointing at museums_test."""
    engine = create_async_engine(_TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Function-scoped AsyncSession that rolls back after every test."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session, session.begin():
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeding_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """Session that commits data for router integration tests, then truncates.

    Use this when seeding data that must be visible to the app_client (which
    opens its own session). Teardown truncates all tables to keep tests isolated.
    """
    session_factory = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        yield session
        # Rollback any failed transaction before truncating
        await session.rollback()
        await session.execute(_TRUNCATE_SQL)
        await session.commit()


def _session_override_factory(engine: AsyncEngine) -> Callable[[], AsyncGenerator[AsyncSession]]:
    """Return a get_session Depends override using the provided engine."""

    async def _override() -> AsyncGenerator[AsyncSession]:
        factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with factory() as session, session.begin():
            yield session
            await session.rollback()

    return _override


@pytest_asyncio.fixture
async def test_app(async_engine: AsyncEngine) -> AsyncGenerator[FastAPI]:
    """Function-scoped FastAPI app with get_session overridden to use test DB."""
    from museums.dependencies import get_session
    from museums.main import create_app

    application = create_app()
    application.dependency_overrides[get_session] = _session_override_factory(async_engine)
    yield application
    application.dependency_overrides.clear()


@pytest_asyncio.fixture
async def app_client(test_app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """Function-scoped AsyncClient wired to the test FastAPI app via ASGITransport."""
    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
