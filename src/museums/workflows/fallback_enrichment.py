"""Merge Wikipedia list entries with Wikidata enrichments.

Wikipedia is the source of truth for inclusion (the 2M visitor threshold is
applied Wikipedia-side, upstream of this step). Wikidata enriches each
Wikipedia row with a city/country/QID and — when available — a historical
``P1174`` visitor time-series.

For each entry this step produces a single ``MuseumEnrichment``:
* Wikidata data if present, otherwise a Wikipedia-only synthetic record.
* Visitor records: Wikidata time-series if non-empty, else the single
  ``(count, year)`` cell scraped from the Wikipedia table.
* City: Wikidata ``P131``-walked QID if available, otherwise the scraped city
  name resolved to a Wikidata QID via ``MediaWikiClient.resolve_qids`` so that
  the downstream population fetch can still run.
"""

from __future__ import annotations

from dataclasses import replace

import structlog

from museums.clients.list_page_parser import MuseumListEntry
from museums.clients.mediawiki_client import MediaWikiClient
from museums.clients.wikidata_client import MuseumEnrichment, VisitorPoint


async def merge_enrichments(
    entries: list[MuseumListEntry],
    wikidata_enrichments: list[MuseumEnrichment],
    mediawiki: MediaWikiClient,
    log: structlog.stdlib.BoundLogger,
) -> list[MuseumEnrichment]:
    """Produce the canonical per-museum enrichment for an ingestion run."""
    enrichments_by_title = {e.wikipedia_title: e for e in wikidata_enrichments}
    preliminary = [_preliminary_enrichment(entry, enrichments_by_title.get(entry.wikipedia_title)) for entry in entries]

    cities_to_resolve = sorted({e.city_label for e in preliminary if e.city_qid is None and e.city_label})
    resolved_city_qids = await mediawiki.resolve_qids(cities_to_resolve) if cities_to_resolve else {}
    log.info(
        "enrichment_merged",
        total=len(preliminary),
        wikidata_covered=len(wikidata_enrichments),
        cities_resolved_from_wikipedia=len(resolved_city_qids),
    )
    return [_apply_resolved_city(e, resolved_city_qids) for e in preliminary]


def _preliminary_enrichment(
    entry: MuseumListEntry,
    wikidata: MuseumEnrichment | None,
) -> MuseumEnrichment:
    wiki_records = _wiki_visitor_records(entry)
    if wikidata is None:
        return MuseumEnrichment(
            wikipedia_title=entry.wikipedia_title,
            museum_qid=None,
            museum_label=entry.display_name,
            city_qid=None,
            city_label=entry.city_name,
            country_label=None,
            visitor_records=wiki_records,
        )
    visitors = wikidata.visitor_records or wiki_records
    city_label = wikidata.city_label or entry.city_name
    return replace(wikidata, visitor_records=visitors, city_label=city_label)


def _apply_resolved_city(enrichment: MuseumEnrichment, resolved: dict[str, str]) -> MuseumEnrichment:
    if enrichment.city_qid is not None or enrichment.city_label is None:
        return enrichment
    qid = resolved.get(enrichment.city_label)
    return replace(enrichment, city_qid=qid) if qid else enrichment


def _wiki_visitor_records(entry: MuseumListEntry) -> list[VisitorPoint]:
    if entry.visitors_count is None or entry.visitors_year is None:
        return []
    return [VisitorPoint(year=entry.visitors_year, visitors=entry.visitors_count)]
