"""Global FastAPI exception handlers mapping domain errors to HTTP responses."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from museums.exceptions import (
    ExternalDataParseError,
    InsufficientDataError,
    MediaWikiUnavailableError,
    NotFoundError,
    RefreshCooldownError,
    WikidataUnavailableError,
)
from museums.schemas.common import ErrorOut


async def handle_not_found(request: Request, exc: NotFoundError) -> JSONResponse:
    body = ErrorOut(detail=str(exc), code="not_found")
    return JSONResponse(status_code=404, content=body.model_dump())


async def handle_refresh_cooldown(request: Request, exc: RefreshCooldownError) -> JSONResponse:
    body = ErrorOut(detail=str(exc), code="refresh_cooldown")
    return JSONResponse(
        status_code=429,
        content=body.model_dump(),
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


async def handle_mediawiki_unavailable(request: Request, exc: MediaWikiUnavailableError) -> JSONResponse:
    detail = f"{exc} [service=mediawiki]"
    body = ErrorOut(detail=detail, code="external_unavailable")
    return JSONResponse(status_code=503, content=body.model_dump())


async def handle_wikidata_unavailable(request: Request, exc: WikidataUnavailableError) -> JSONResponse:
    detail = f"{exc} [service=wikidata]"
    body = ErrorOut(detail=detail, code="external_unavailable")
    return JSONResponse(status_code=503, content=body.model_dump())


async def handle_external_parse_error(request: Request, exc: ExternalDataParseError) -> JSONResponse:
    body = ErrorOut(detail=str(exc), code="external_parse_error")
    return JSONResponse(status_code=502, content=body.model_dump())


async def handle_insufficient_data(request: Request, exc: InsufficientDataError) -> JSONResponse:
    body = ErrorOut(detail=str(exc), code="insufficient_data")
    return JSONResponse(status_code=422, content=body.model_dump())
