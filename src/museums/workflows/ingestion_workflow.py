"""Ingestion workflow — orchestrates clients + repositories under one transaction."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from museums.clients.mediawiki_client import MediaWikiClient
from museums.clients.wikidata_client import MuseumEnrichment, PopulationPoint, WikidataClient
from museums.config import Settings
from museums.exceptions import RefreshCooldownError
from museums.repositories.city_repository import CityRepository
from museums.repositories.museum_repository import MuseumRepository
from museums.repositories.population_record_repository import PopulationRecordRepository
from museums.repositories.refresh_state_repository import RefreshStateRepository
from museums.repositories.visitor_record_repository import VisitorRecordRepository
from museums.workflows.fallback_enrichment import merge_enrichments

_log = structlog.get_logger("ingestion")


@dataclass(slots=True, frozen=True)
class IngestionDeps:
    """Holds the five repositories consumed by IngestionWorkflow."""

    city_repo: CityRepository
    museum_repo: MuseumRepository
    visitor_repo: VisitorRecordRepository
    population_repo: PopulationRecordRepository
    refresh_repo: RefreshStateRepository


@dataclass(frozen=True)
class RefreshSummary:
    """Counts and timestamps returned after a successful refresh."""

    museums_refreshed: int
    cities_refreshed: int
    visitor_records_upserted: int
    population_records_upserted: int
    started_at: datetime
    finished_at: datetime


class IngestionWorkflow:
    """Orchestrates a full data refresh under a single explicit transaction."""

    def __init__(
        self,
        mediawiki: MediaWikiClient,
        wikidata: WikidataClient,
        session: AsyncSession,
        settings: Settings,
        deps: IngestionDeps,
    ) -> None:
        self._mediawiki = mediawiki
        self._wikidata = wikidata
        self._session = session
        self._settings = settings
        self._deps = deps

    async def refresh(self, *, force: bool) -> RefreshSummary:
        """Run a full data refresh. Commits on success, rolls back on failure."""
        started_at = datetime.now(UTC)
        log = _log.bind(correlation_id=str(uuid.uuid4())[:8])
        await self._check_cooldown(force)
        log.info("ingestion_started")
        try:
            summary = await self._run(started_at, log)
        except Exception:
            await self._session.rollback()
            log.error("ingestion_rolled_back")
            raise
        await self._session.commit()
        log.info("ingestion_committed", museums=summary.museums_refreshed, cities=summary.cities_refreshed)
        return summary

    async def _check_cooldown(self, force: bool) -> None:
        state = await self._deps.refresh_repo.get()
        if state.last_refresh_at is None or force:
            return
        elapsed = datetime.now(UTC) - state.last_refresh_at
        cooldown = timedelta(hours=self._settings.refresh_cooldown_hours)
        if elapsed < cooldown:
            raise RefreshCooldownError(remaining_seconds=int((cooldown - elapsed).total_seconds()))

    async def _fetch_data(
        self,
        log: structlog.stdlib.BoundLogger,
    ) -> tuple[list[MuseumEnrichment], dict[str, list[PopulationPoint]]]:
        log.info("fetching_museum_list")
        entries = await self._mediawiki.fetch_museum_list()
        log.info("museum_list_fetched", count=len(entries))

        # Wikipedia is the source of truth for inclusion; Wikidata is purely
        # enrichment. Filter the scraped visitor count against the configured
        # threshold before hitting SPARQL so we only enrich museums that will
        # actually be persisted.
        threshold = self._settings.museum_visitor_threshold
        filtered = [e for e in entries if e.visitors_count is not None and e.visitors_count > threshold]
        log.info("wikipedia_threshold_applied", kept=len(filtered), total=len(entries), threshold=threshold)

        log.info("fetching_museum_enrichment")
        wd_enrichments = await self._wikidata.fetch_museum_enrichment([e.wikipedia_title for e in filtered])
        log.info("museum_enrichment_fetched", count=len(wd_enrichments))

        enrichments = await merge_enrichments(filtered, wd_enrichments, self._mediawiki, log)

        unique_city_qids = list({e.city_qid for e in enrichments if e.city_qid})
        log.info("fetching_city_populations", city_count=len(unique_city_qids))
        populations = await self._wikidata.fetch_city_populations(unique_city_qids)
        log.info("city_populations_fetched", city_count=len(populations))
        return enrichments, populations

    async def _run(
        self,
        started_at: datetime,
        log: structlog.stdlib.BoundLogger,
    ) -> RefreshSummary:
        enrichments, populations = await self._fetch_data(log)
        # Wipe existing data AFTER the fetch succeeds — replaces the DB with
        # the current Wikidata response, preventing stale rows from surviving
        # when a filter/query change shrinks the response. If a fetch fails,
        # nothing gets wiped (failure rolls back the outer transaction).
        # Delete order: museums first (cascades to visitor_records), then
        # cities (cascades to population_records).
        await self._deps.museum_repo.delete_all()
        await self._deps.city_repo.delete_all()
        log.info("wiped_existing_data_before_reingest")
        qid_to_city_id = await self._upsert_cities(enrichments)
        museums_count, visitor_count = await self._upsert_museums_and_visitors(enrichments, qid_to_city_id)
        pop_count = await self._upsert_populations(populations)
        await self._deps.refresh_repo.mark_refreshed(museums=museums_count, cities=len(qid_to_city_id))
        return RefreshSummary(
            museums_refreshed=museums_count,
            cities_refreshed=len(qid_to_city_id),
            visitor_records_upserted=visitor_count,
            population_records_upserted=pop_count,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    async def _upsert_cities(self, enrichments: list[MuseumEnrichment]) -> dict[str, int]:
        qid_to_city_id: dict[str, int] = {}
        for enrichment in enrichments:
            if not enrichment.city_qid or enrichment.city_qid in qid_to_city_id:
                continue
            city = await self._deps.city_repo.upsert_by_qid(
                qid=enrichment.city_qid,
                name=enrichment.city_label or enrichment.city_qid,
                country=enrichment.country_label,
            )
            qid_to_city_id[enrichment.city_qid] = city.id
        return qid_to_city_id

    async def _upsert_museums_and_visitors(
        self,
        enrichments: list[MuseumEnrichment],
        qid_to_city_id: dict[str, int],
    ) -> tuple[int, int]:
        museum_count = 0
        visitor_count = 0
        for enrichment in enrichments:
            city_id = qid_to_city_id.get(enrichment.city_qid) if enrichment.city_qid else None
            museum = await self._deps.museum_repo.upsert_by_name(
                name=enrichment.museum_label,
                wikipedia_title=enrichment.wikipedia_title,
                wikidata_qid=enrichment.museum_qid,
                city_id=city_id,
                country=enrichment.country_label,
            )
            museum_count += 1
            records = [(vp.year, vp.visitors) for vp in enrichment.visitor_records]
            visitor_count += await self._deps.visitor_repo.upsert_many(museum.id, records)
        return museum_count, visitor_count

    async def _upsert_populations(self, populations: dict[str, list[PopulationPoint]]) -> int:
        pop_count = 0
        for qid, points in populations.items():
            city = await self._deps.city_repo.get_by_qid(qid)
            if city is None:
                continue
            records = [(p.year, p.population) for p in points]
            pop_count += await self._deps.population_repo.upsert_many(city.id, records)
        return pop_count
