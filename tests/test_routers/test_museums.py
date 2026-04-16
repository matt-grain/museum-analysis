"""Integration tests for GET /museums."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import build_city, build_museum, build_visitor_record


@pytest.mark.asyncio
async def test_list_museums_returns_paginated_response(
    seeding_session: AsyncSession, app_client: httpx.AsyncClient
) -> None:
    # Arrange
    city = await build_city(seeding_session)
    m1 = await build_museum(seeding_session, name="Louvre", qid="Q001")
    m2 = await build_museum(seeding_session, name="British Museum", qid="Q002")
    m3 = await build_museum(seeding_session, name="Smithsonian", qid="Q003")
    await build_visitor_record(seeding_session, museum=m1)
    await build_visitor_record(seeding_session, museum=m2)
    await build_visitor_record(seeding_session, museum=m3)
    await seeding_session.commit()

    # Act
    response = await app_client.get("/museums")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3
    assert body["pagination"]["total"] == 3
    _ = city  # seeded for completeness; museums don't require a city


@pytest.mark.asyncio
async def test_list_museums_limit_caps_at_200(app_client: httpx.AsyncClient) -> None:
    # Act
    response = await app_client.get("/museums?limit=500")

    # Assert
    assert response.status_code == 422
