"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text

from museums.config import get_settings
from museums.logging_config import setup_logging

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown."""
    settings = get_settings()
    setup_logging(settings.log_level)

    engine = create_async_engine(str(settings.database_url), echo=settings.database_echo)

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    logger.info("database_connected", url=str(settings.database_url))

    yield

    await engine.dispose()
    logger.info("database_disconnected")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    return FastAPI(
        title="Museums API",
        version="0.1.0",
        lifespan=lifespan,
    )


app = create_app()
