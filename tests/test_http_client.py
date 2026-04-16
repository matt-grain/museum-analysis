"""Tests for src/museums/http_client.py."""

from __future__ import annotations

import httpx
import pytest
import respx

from museums.http_client import retry_policy, should_retry


def _make_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError for a given status code."""
    request = httpx.Request("GET", "https://example.com/test")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Server error {status_code}",
        request=request,
        response=response,
    )


def test_should_retry_returns_true_for_5xx() -> None:
    """should_retry must return True for HTTP 503 status errors."""
    exc = _make_status_error(503)

    assert should_retry(exc) is True


def test_should_retry_returns_false_for_4xx() -> None:
    """should_retry must return False for HTTP 404 — client errors are not retried."""
    exc = _make_status_error(404)

    assert should_retry(exc) is False


def test_should_retry_returns_true_for_connect_error() -> None:
    """should_retry must return True for httpx.ConnectError."""
    exc = httpx.ConnectError("connection refused")

    assert should_retry(exc) is True


@pytest.mark.asyncio
async def test_retry_policy_stops_after_max_attempts() -> None:
    """retry_policy must exhaust max_attempts and re-raise on permanent 503."""
    call_count = 0

    with respx.mock:
        route = respx.get("https://example.com/always-503").mock(return_value=httpx.Response(503))

        async with httpx.AsyncClient() as client:
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                async for attempt in retry_policy(max_attempts=3):
                    with attempt:
                        call_count += 1
                        response = await client.get("https://example.com/always-503")
                        response.raise_for_status()

        assert exc_info.value.response.status_code == 503
        assert route.call_count == 3
