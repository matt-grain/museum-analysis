"""Integration test for GET /health."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_returns_ok_when_db_reachable(app_client: httpx.AsyncClient) -> None:
    # Act
    response = await app_client.get("/health")

    # Assert
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
