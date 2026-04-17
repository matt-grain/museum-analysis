"""FastAPI Depends() chains — wiring only, no business logic."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from museums.clients.mediawiki_client import MediaWikiClient
from museums.clients.wikidata_client import WikidataClient
from museums.config import Settings, get_settings
from museums.repositories.city_repository import CityRepository
from museums.repositories.health_repository import HealthRepository
from museums.repositories.museum_repository import MuseumRepository
from museums.repositories.population_record_repository import PopulationRecordRepository
from museums.repositories.refresh_state_repository import RefreshStateRepository
from museums.repositories.visitor_record_repository import VisitorRecordRepository
from museums.services.city_query_service import CityQueryService
from museums.services.harmonization_service import HarmonizationService
from museums.services.health_service import HealthService
from museums.services.museum_query_service import MuseumQueryService
from museums.services.regression_service import RegressionService
from museums.workflows.ingestion_workflow import IngestionDeps, IngestionWorkflow

# ── Settings ──────────────────────────────────────────────────────────────────

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ── Session ───────────────────────────────────────────────────────────────────


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession from the lifespan-created session factory."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


# ── HTTP client ───────────────────────────────────────────────────────────────


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient stored on app.state."""
    client: httpx.AsyncClient = request.app.state.http_client
    return client


HttpClientDep = Annotated[httpx.AsyncClient, Depends(get_http_client)]


# ── Repositories ──────────────────────────────────────────────────────────────


async def get_city_repo(session: SessionDep) -> CityRepository:
    return CityRepository(session)


async def get_museum_repo(session: SessionDep) -> MuseumRepository:
    return MuseumRepository(session)


async def get_visitor_repo(session: SessionDep) -> VisitorRecordRepository:
    return VisitorRecordRepository(session)


async def get_population_repo(session: SessionDep) -> PopulationRecordRepository:
    return PopulationRecordRepository(session)


async def get_refresh_repo(session: SessionDep) -> RefreshStateRepository:
    return RefreshStateRepository(session)


async def get_health_repo(session: SessionDep) -> HealthRepository:
    return HealthRepository(session)


CityRepositoryDep = Annotated[CityRepository, Depends(get_city_repo)]
MuseumRepositoryDep = Annotated[MuseumRepository, Depends(get_museum_repo)]
VisitorRecordRepositoryDep = Annotated[VisitorRecordRepository, Depends(get_visitor_repo)]
PopulationRecordRepositoryDep = Annotated[PopulationRecordRepository, Depends(get_population_repo)]
RefreshStateRepositoryDep = Annotated[RefreshStateRepository, Depends(get_refresh_repo)]
HealthRepoDep = Annotated[HealthRepository, Depends(get_health_repo)]


# ── Clients ───────────────────────────────────────────────────────────────────


async def get_mediawiki_client(client: HttpClientDep, settings: SettingsDep) -> MediaWikiClient:
    return MediaWikiClient(client=client, settings=settings)


async def get_wikidata_client(client: HttpClientDep, settings: SettingsDep) -> WikidataClient:
    return WikidataClient(client=client, settings=settings)


MediaWikiClientDep = Annotated[MediaWikiClient, Depends(get_mediawiki_client)]
WikidataClientDep = Annotated[WikidataClient, Depends(get_wikidata_client)]


# ── Ingestion deps factory ────────────────────────────────────────────────────


async def get_ingestion_deps(
    city_repo: CityRepositoryDep,
    museum_repo: MuseumRepositoryDep,
    visitor_repo: VisitorRecordRepositoryDep,
    population_repo: PopulationRecordRepositoryDep,
    refresh_repo: RefreshStateRepositoryDep,
) -> IngestionDeps:
    return IngestionDeps(
        city_repo=city_repo,
        museum_repo=museum_repo,
        visitor_repo=visitor_repo,
        population_repo=population_repo,
        refresh_repo=refresh_repo,
    )


IngestionDepsDep = Annotated[IngestionDeps, Depends(get_ingestion_deps)]


# ── Workflow factory ──────────────────────────────────────────────────────────


async def get_ingestion_workflow(
    mediawiki: MediaWikiClientDep,
    wikidata: WikidataClientDep,
    session: SessionDep,
    settings: SettingsDep,
    deps: IngestionDepsDep,
) -> IngestionWorkflow:
    return IngestionWorkflow(
        mediawiki=mediawiki,
        wikidata=wikidata,
        session=session,
        settings=settings,
        deps=deps,
    )


IngestionWorkflowDep = Annotated[IngestionWorkflow, Depends(get_ingestion_workflow)]


# ── Service factories ─────────────────────────────────────────────────────────


async def get_museum_query_service(museum_repo: MuseumRepositoryDep) -> MuseumQueryService:
    return MuseumQueryService(museum_repo=museum_repo)


async def get_city_query_service(
    city_repo: CityRepositoryDep,
    population_repo: PopulationRecordRepositoryDep,
) -> CityQueryService:
    return CityQueryService(city_repo=city_repo, population_repo=population_repo)


async def get_harmonization_service(
    museum_repo: MuseumRepositoryDep,
    visitor_repo: VisitorRecordRepositoryDep,
    population_repo: PopulationRecordRepositoryDep,
) -> HarmonizationService:
    return HarmonizationService(
        museum_repo=museum_repo,
        visitor_repo=visitor_repo,
        population_repo=population_repo,
    )


MuseumQueryServiceDep = Annotated[MuseumQueryService, Depends(get_museum_query_service)]
CityQueryServiceDep = Annotated[CityQueryService, Depends(get_city_query_service)]
HarmonizationServiceDep = Annotated[HarmonizationService, Depends(get_harmonization_service)]


async def get_regression_service(
    harmonization: HarmonizationServiceDep,
) -> RegressionService:
    return RegressionService(harmonization=harmonization)


async def get_health_service(repo: HealthRepoDep) -> HealthService:
    return HealthService(repo=repo)


RegressionServiceDep = Annotated[RegressionService, Depends(get_regression_service)]
HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
