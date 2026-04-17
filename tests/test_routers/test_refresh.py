"""Integration tests for POST /refresh."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from museums.dependencies import get_ingestion_workflow
from museums.enums.external_source import ExternalSource
from museums.exceptions import (
    ExternalDataParseError,
    MediaWikiUnavailableError,
    NotFoundError,
    RefreshCooldownError,
    WikidataUnavailableError,
)
from museums.workflows.ingestion_workflow import RefreshSummary

_FIXED_SUMMARY = RefreshSummary(
    museums_refreshed=5,
    cities_refreshed=3,
    visitor_records_upserted=10,
    population_records_upserted=12,
    started_at=datetime(2024, 1, 1, tzinfo=UTC),
    finished_at=datetime(2024, 1, 1, 0, 0, 5, tzinfo=UTC),
)


def _make_workflow_stub(summary: RefreshSummary | None = None, exc: Exception | None = None) -> object:
    stub = AsyncMock()
    if exc is not None:
        stub.refresh.side_effect = exc
    else:
        stub.refresh.return_value = summary or _FIXED_SUMMARY
    return stub


@pytest.mark.asyncio
async def test_refresh_returns_202_with_summary_on_success(test_app: FastAPI, app_client: httpx.AsyncClient) -> None:
    # Arrange
    test_app.dependency_overrides[get_ingestion_workflow] = lambda: _make_workflow_stub()

    # Act
    response = await app_client.post("/refresh")

    # Assert
    assert response.status_code == 202
    body = response.json()
    assert body["museums_refreshed"] == 5
    assert body["cities_refreshed"] == 3
    assert body["visitor_records_upserted"] == 10
    assert body["duration_seconds"] == 5.0


@pytest.mark.asyncio
async def test_refresh_returns_429_with_retry_after_on_cooldown(
    test_app: FastAPI, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    test_app.dependency_overrides[get_ingestion_workflow] = lambda: _make_workflow_stub(
        exc=RefreshCooldownError(remaining_seconds=3600)
    )

    # Act
    response = await app_client.post("/refresh")

    # Assert
    assert response.status_code == 429
    assert response.headers["retry-after"] == "3600"
    assert response.json()["code"] == "refresh_cooldown"


@pytest.mark.parametrize(
    ("exc", "expected_service"),
    [
        (MediaWikiUnavailableError("mediawiki down"), "mediawiki"),
        (WikidataUnavailableError("wikidata down"), "wikidata"),
    ],
)
@pytest.mark.asyncio
async def test_refresh_returns_503_when_external_service_unavailable(
    test_app: FastAPI,
    app_client: httpx.AsyncClient,
    exc: Exception,
    expected_service: str,
) -> None:
    # Arrange
    test_app.dependency_overrides[get_ingestion_workflow] = lambda: _make_workflow_stub(exc=exc)

    # Act
    response = await app_client.post("/refresh")

    # Assert
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "external_unavailable"
    assert expected_service in body["detail"]


@pytest.mark.asyncio
async def test_refresh_with_force_param_calls_workflow_with_force_true(
    test_app: FastAPI, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    stub = _make_workflow_stub()
    test_app.dependency_overrides[get_ingestion_workflow] = lambda: stub

    # Act
    response = await app_client.post("/refresh?force=true")

    # Assert
    assert response.status_code == 202
    stub.refresh.assert_called_once_with(force=True)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_refresh_returns_404_when_not_found_error_raised(
    test_app: FastAPI, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    test_app.dependency_overrides[get_ingestion_workflow] = lambda: _make_workflow_stub(
        exc=NotFoundError("museum", 999)
    )

    # Act
    response = await app_client.post("/refresh")

    # Assert
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


@pytest.mark.asyncio
async def test_refresh_returns_502_when_external_parse_error_raised(
    test_app: FastAPI, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    test_app.dependency_overrides[get_ingestion_workflow] = lambda: _make_workflow_stub(
        exc=ExternalDataParseError(source=ExternalSource.WIKIDATA, detail="bad json")
    )

    # Act
    response = await app_client.post("/refresh")

    # Assert
    assert response.status_code == 502
    assert response.json()["code"] == "external_parse_error"
