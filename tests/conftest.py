"""Shared fixtures for the museums test suite."""

from __future__ import annotations

import pytest

from museums.config import Settings


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
