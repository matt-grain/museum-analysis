"""Shared httpx.AsyncClient factory with tenacity retry/backoff logic."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import tenacity

from museums.config import Settings

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def build_timeout(settings: Settings) -> httpx.Timeout:
    """Build httpx.Timeout from settings."""
    return httpx.Timeout(
        connect=settings.http_connect_timeout_seconds,
        read=settings.http_read_timeout_seconds,
        write=10.0,
        pool=5.0,
    )


@asynccontextmanager
async def http_client_lifespan(settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """Yield a shared httpx.AsyncClient and close it on exit."""
    timeout = build_timeout(settings)
    headers = {"User-Agent": settings.user_agent}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        yield client


def should_retry(exc: BaseException) -> bool:
    """Return True if the exception is retryable."""
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)) or (
        isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in _RETRYABLE_STATUS_CODES
    )


def retry_policy(max_attempts: int) -> tenacity.AsyncRetrying:
    """Build an AsyncRetrying policy with exponential backoff."""
    return tenacity.AsyncRetrying(
        stop=tenacity.stop_after_attempt(max_attempts),
        wait=tenacity.wait_exponential(multiplier=1, min=1, max=8),
        retry=tenacity.retry_if_exception(should_retry),
        reraise=True,
    )
