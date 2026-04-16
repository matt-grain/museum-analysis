"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text

from museums.config import get_settings
from museums.exception_handlers import (
    handle_external_parse_error,
    handle_insufficient_data,
    handle_mediawiki_unavailable,
    handle_not_found,
    handle_refresh_cooldown,
    handle_wikidata_unavailable,
)
from museums.exceptions import (
    ExternalDataParseError,
    InsufficientDataError,
    MediaWikiUnavailableError,
    NotFoundError,
    RefreshCooldownError,
    WikidataUnavailableError,
)
from museums.http_client import http_client_lifespan
from museums.logging_config import setup_logging
from museums.routers import api_router

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

    async with http_client_lifespan(settings) as client:
        app.state.engine = engine
        app.state.http_client = client
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("database_disconnected")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Museums API",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.include_router(api_router)

    application.add_exception_handler(NotFoundError, handle_not_found)  # type: ignore[arg-type]
    application.add_exception_handler(RefreshCooldownError, handle_refresh_cooldown)  # type: ignore[arg-type]
    application.add_exception_handler(MediaWikiUnavailableError, handle_mediawiki_unavailable)  # type: ignore[arg-type]
    application.add_exception_handler(WikidataUnavailableError, handle_wikidata_unavailable)  # type: ignore[arg-type]
    application.add_exception_handler(ExternalDataParseError, handle_external_parse_error)  # type: ignore[arg-type]
    application.add_exception_handler(InsufficientDataError, handle_insufficient_data)  # type: ignore[arg-type]

    return application


app = create_app()
