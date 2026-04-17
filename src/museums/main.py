"""FastAPI application factory and lifespan."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    logger.info("database_connected", url=str(settings.database_url))

    async with http_client_lifespan(settings) as client:
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.http_client = client
        try:
            yield
        finally:
            await engine.dispose()
            logger.info("database_disconnected")


_OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "health", "description": "Liveness / readiness checks."},
    {"name": "refresh", "description": "Trigger and monitor data re-ingestion from Wikipedia + Wikidata."},
    {"name": "museums", "description": "Read-only: the ingested museum list with visitor records."},
    {"name": "cities", "description": "Read-only: cities with their population time series."},
    {"name": "harmonized", "description": "Per-museum (visitor year -> estimated city population) projections."},
    {"name": "regression", "description": "Log-log OLS fit on the harmonized dataset."},
]


def _register_exception_handlers(application: FastAPI) -> None:
    # FastAPI's add_exception_handler() typestub expects type[Exception] but our
    # domain-error subclasses are correctly typed as DomainError descendants.
    # This is a known starlette/fastapi stub limitation; the runtime behavior is correct.
    application.add_exception_handler(NotFoundError, handle_not_found)  # type: ignore[arg-type]
    application.add_exception_handler(RefreshCooldownError, handle_refresh_cooldown)  # type: ignore[arg-type]
    application.add_exception_handler(MediaWikiUnavailableError, handle_mediawiki_unavailable)  # type: ignore[arg-type]
    application.add_exception_handler(WikidataUnavailableError, handle_wikidata_unavailable)  # type: ignore[arg-type]
    application.add_exception_handler(ExternalDataParseError, handle_external_parse_error)  # type: ignore[arg-type]
    application.add_exception_handler(InsufficientDataError, handle_insufficient_data)  # type: ignore[arg-type]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(
        title="Museums API",
        version="0.1.0",
        description=(
            "A small, harmonized dataset of high-traffic museums (>2M visitors/year) "
            "and the populations of the cities they sit in, exposed as a FastAPI "
            "service with a log-log regression endpoint. See /docs for the OpenAPI "
            "UI and /harmonized + /regression for the analysis endpoints."
        ),
        contact={"name": "matt-grain", "url": "https://github.com/matt-grain/museum-analysis"},
        openapi_tags=_OPENAPI_TAGS,
        lifespan=lifespan,
    )
    application.include_router(api_router)
    _register_exception_handlers(application)
    return application


app = create_app()
