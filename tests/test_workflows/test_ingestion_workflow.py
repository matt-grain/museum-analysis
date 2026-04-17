"""Tests for IngestionWorkflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from museums.clients.population_parsing import PopulationPoint
from museums.config import Settings
from museums.exceptions import MediaWikiUnavailableError, RefreshCooldownError, WikidataUnavailableError
from museums.models.city import City
from museums.models.museum import Museum
from museums.models.refresh_state import RefreshState
from museums.repositories.city_repository import CityRepository
from museums.repositories.museum_repository import MuseumRepository
from museums.repositories.population_record_repository import PopulationRecordRepository
from museums.repositories.refresh_state_repository import RefreshStateRepository
from museums.repositories.visitor_record_repository import VisitorRecordRepository
from museums.workflows.ingestion_workflow import IngestionDeps, IngestionWorkflow
from tests.factories import make_museum_enrichment, make_museum_list_entry

_TEST_SETTINGS = Settings(
    database_url="postgresql+asyncpg://museums:museums@localhost:5432/museums_test",  # type: ignore[arg-type]
    refresh_cooldown_hours=24,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_mediawiki_stub() -> AsyncMock:
    stub = AsyncMock()
    stub.fetch_museum_list.return_value = [
        make_museum_list_entry("Louvre"),
        make_museum_list_entry("British Museum"),
    ]
    return stub


def _make_wikidata_stub() -> AsyncMock:
    stub = AsyncMock()
    stub.fetch_museum_enrichment.return_value = [
        make_museum_enrichment(
            title="Louvre",
            museum_qid="Q19675",
            museum_label="Louvre",
            city_qid="Q90",
            city_label="Paris",
            country_label="France",
            visitors=8_900_000,
            year=2023,
        ),
        make_museum_enrichment(
            title="British Museum",
            museum_qid="Q6373",
            museum_label="British Museum",
            city_qid="Q84",
            city_label="London",
            country_label="United Kingdom",
            visitors=5_820_860,
            year=2023,
        ),
    ]
    stub.fetch_city_populations.return_value = {
        "Q90": [PopulationPoint(year=2019, population=2_161_000), PopulationPoint(year=2023, population=2_145_906)],
        "Q84": [PopulationPoint(year=2019, population=8_908_081), PopulationPoint(year=2022, population=8_799_800)],
    }
    return stub


def _make_deps(session: AsyncSession) -> IngestionDeps:
    return IngestionDeps(
        city_repo=CityRepository(session),
        museum_repo=MuseumRepository(session),
        visitor_repo=VisitorRecordRepository(session),
        population_repo=PopulationRecordRepository(session),
        refresh_repo=RefreshStateRepository(session),
    )


def _make_workflow(session: AsyncSession) -> IngestionWorkflow:
    return IngestionWorkflow(
        mediawiki=_make_mediawiki_stub(),  # type: ignore[arg-type]
        wikidata=_make_wikidata_stub(),  # type: ignore[arg-type]
        session=session,
        settings=_TEST_SETTINGS,
        deps=_make_deps(session),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_persists_all_entities_on_happy_path(workflow_session: AsyncSession) -> None:
    """refresh commits cities, museums, visitor records, population records, and refresh_state."""
    workflow = _make_workflow(workflow_session)

    summary = await workflow.refresh(force=True)

    result = await workflow_session.execute(select(Museum))
    museums = list(result.scalars().all())
    assert len(museums) == 2

    result = await workflow_session.execute(select(City))
    cities = list(result.scalars().all())
    assert len(cities) == 2

    result = await workflow_session.execute(select(RefreshState).where(RefreshState.id == 1))
    state = result.scalar_one()
    assert state.last_refresh_at is not None

    assert summary.museums_refreshed == 2
    assert summary.cities_refreshed == 2
    assert summary.visitor_records_upserted == 2
    assert summary.population_records_upserted == 4


@pytest.mark.asyncio
async def test_refresh_within_cooldown_raises_refresh_cooldown_error(workflow_session: AsyncSession) -> None:
    """refresh(force=False) raises RefreshCooldownError when last_refresh_at is recent."""
    refresh_repo = RefreshStateRepository(workflow_session)
    state = await refresh_repo.get()
    state.last_refresh_at = datetime.now(UTC) - timedelta(hours=1)
    await workflow_session.commit()

    workflow = _make_workflow(workflow_session)

    with pytest.raises(RefreshCooldownError) as exc_info:
        await workflow.refresh(force=False)

    assert exc_info.value.retry_after_seconds > 0


@pytest.mark.asyncio
async def test_refresh_with_force_bypasses_cooldown(workflow_session: AsyncSession) -> None:
    """refresh(force=True) completes even when last_refresh_at is recent."""
    refresh_repo = RefreshStateRepository(workflow_session)
    state = await refresh_repo.get()
    state.last_refresh_at = datetime.now(UTC) - timedelta(minutes=30)
    await workflow_session.commit()

    workflow = _make_workflow(workflow_session)
    summary = await workflow.refresh(force=True)

    assert summary.museums_refreshed == 2


@pytest.mark.asyncio
async def test_refresh_rolls_back_on_client_failure(workflow_session: AsyncSession) -> None:
    """refresh rolls back the transaction when wikidata raises WikidataUnavailableError."""
    wikidata_stub = AsyncMock()
    wikidata_stub.fetch_museum_enrichment.side_effect = WikidataUnavailableError("wikidata down")

    workflow = IngestionWorkflow(
        mediawiki=_make_mediawiki_stub(),  # type: ignore[arg-type]
        wikidata=wikidata_stub,  # type: ignore[arg-type]
        session=workflow_session,
        settings=_TEST_SETTINGS,
        deps=_make_deps(workflow_session),
    )

    with pytest.raises(WikidataUnavailableError):
        await workflow.refresh(force=True)

    result = await workflow_session.execute(select(Museum))
    assert not list(result.scalars().all())

    result = await workflow_session.execute(select(City))
    assert not list(result.scalars().all())


@pytest.mark.asyncio
async def test_refresh_rolls_back_on_mediawiki_failure(workflow_session: AsyncSession) -> None:
    """refresh rolls back when the MediaWiki client raises MediaWikiUnavailableError."""
    mediawiki_stub = AsyncMock()
    mediawiki_stub.fetch_museum_list.side_effect = MediaWikiUnavailableError("mediawiki down")

    workflow = IngestionWorkflow(
        mediawiki=mediawiki_stub,  # type: ignore[arg-type]
        wikidata=_make_wikidata_stub(),  # type: ignore[arg-type]
        session=workflow_session,
        settings=_TEST_SETTINGS,
        deps=_make_deps(workflow_session),
    )

    with pytest.raises(MediaWikiUnavailableError):
        await workflow.refresh(force=True)

    # No museums should be persisted — transaction rolled back
    museum_repo = MuseumRepository(workflow_session)
    _, total = await museum_repo.list_paginated(skip=0, limit=1000)
    assert total == 0


@pytest.mark.asyncio
async def test_refresh_upserts_idempotently_on_second_run(workflow_session: AsyncSession) -> None:
    """Calling refresh twice with the same data does not create duplicate rows."""
    workflow = _make_workflow(workflow_session)

    await workflow.refresh(force=True)
    await workflow.refresh(force=True)

    result = await workflow_session.execute(select(Museum))
    museums = list(result.scalars().all())
    assert len(museums) == 2

    result = await workflow_session.execute(select(City))
    cities = list(result.scalars().all())
    assert len(cities) == 2
