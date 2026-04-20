"""Wikidata client — fetches museum enrichment and city populations via SPARQL."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from museums.clients.population_parsing import PopulationPoint, parse_populations
from museums.config import Settings
from museums.enums.external_source import ExternalSource
from museums.exceptions import ExternalDataParseError, WikidataUnavailableError
from museums.http_client import retry_policy

_SPARQL_ACCEPT = "application/sparql-results+json"

# Wikidata "city-like" classes accepted when walking P131* up from a museum.
#   - Q515    "city"                — e.g. Paris (Q90), Madrid (Q2807).
#   - Q159313 "urban agglomeration" — e.g. Greater London (Q23306). Required
#     because London boroughs' P131 chain never passes through Q515; they walk
#     up to Greater London, typed as urban agglomeration.
_CITY_CLASS_VALUES = "wd:Q515 wd:Q159313"

# Enrichment is unfiltered: Wikipedia's table is the source of truth for
# inclusion (the 2M threshold is applied client-side against the scraped
# ``visitors_count``). Wikidata supplies city/country + a visitor time-series
# when available; missing P1174 is normal and gets filled in from Wikipedia's
# single data point by the merge step in the workflow.
_MUSEUM_QUERY_TEMPLATE = (
    "SELECT ?museum ?museumLabel ?city ?cityLabel ?country ?countryLabel ?title ?visitors ?year WHERE {{"
    " VALUES ?title {{ {values} }}"
    " ?article schema:about ?museum ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title ."
    " OPTIONAL {{ ?museum wdt:P17 ?country . }}"
    " OPTIONAL {{"
    "  ?museum p:P1174 ?vStatement . ?vStatement ps:P1174 ?visitors ."
    "  OPTIONAL {{ ?vStatement pq:P585 ?date . BIND(YEAR(?date) AS ?year) }}"
    "  FILTER(!BOUND(?year) || ?year >= 2000)"
    " }}"
    " OPTIONAL {{"
    "  ?museum wdt:P131* ?city ."
    "  VALUES ?cityType {{ {city_classes} }}"
    "  ?city wdt:P31/wdt:P279* ?cityType ."
    " }}"
    " OPTIONAL {{ ?museum wdt:P159 ?city }}"
    ' SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }} }}'
)


@dataclass(frozen=True)
class VisitorPoint:
    """A single (year, visitors) data point for a museum."""

    year: int
    visitors: int


@dataclass(frozen=True)
class MuseumEnrichment:
    """Structured enrichment for a single museum.

    ``museum_qid`` is nullable because Wikipedia-derived fallback rows (museums
    with no P1174 statement on Wikidata) have no linked Wikidata item that we
    want to persist — the museum is stored by name, not by QID, in that case.
    """

    wikipedia_title: str
    museum_qid: str | None
    museum_label: str
    city_qid: str | None
    city_label: str | None
    country_label: str | None
    visitor_records: list[VisitorPoint] = field(default_factory=list)  # type: ignore[assignment]
    # frozen=True + default_factory is valid at runtime; pyright incorrectly rejects it


def _chunk[T](seq: Sequence[T], size: int = 50) -> Iterator[list[T]]:
    """Yield successive fixed-size chunks from seq."""
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def _val(binding: dict[str, Any], key: str) -> str | None:
    entry = binding.get(key)
    return str(entry.get("value", "")) if entry is not None else None


def _accumulate_enrichment_row(grouped: dict[tuple[str, str], dict[str, Any]], row: dict[str, Any]) -> None:
    """Merge one SPARQL binding row into the grouped enrichment dict."""
    museum_qid = (_val(row, "museum") or "").split("/")[-1]
    title = _val(row, "title") or ""
    key = (title, museum_qid)
    if key not in grouped:
        grouped[key] = {
            "wikipedia_title": title,
            "museum_qid": museum_qid,
            "museum_label": _val(row, "museumLabel") or "",
            "city_qid": None,
            "city_label": _val(row, "cityLabel"),
            "country_label": _val(row, "countryLabel"),
            "visitor_records": {},
        }
    entry = grouped[key]
    city_uri = _val(row, "city")
    if city_uri and entry["city_qid"] is None:
        entry["city_qid"] = city_uri.split("/")[-1]
    year_str, visitors_str = _val(row, "year"), _val(row, "visitors")
    if year_str and visitors_str:
        yr, vis = int(year_str), int(float(visitors_str))
        entry["visitor_records"][yr] = max(entry["visitor_records"].get(yr, 0), vis)


def _build_enrichment(e: dict[str, Any]) -> MuseumEnrichment:
    return MuseumEnrichment(
        wikipedia_title=e["wikipedia_title"],
        museum_qid=e["museum_qid"],
        museum_label=e["museum_label"],
        city_qid=e["city_qid"],
        city_label=e["city_label"],
        country_label=e["country_label"],
        visitor_records=[VisitorPoint(year=y, visitors=v) for y, v in sorted(e["visitor_records"].items())],
    )


def _parse_enrichments(bindings: list[dict[str, Any]]) -> list[MuseumEnrichment]:
    """Group SPARQL rows by (title, museum QID) into MuseumEnrichment objects."""
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in bindings:
        _accumulate_enrichment_row(grouped, row)
    return [_build_enrichment(e) for e in grouped.values()]


class WikidataClient:
    """Fetches structured museum and city data via SPARQL."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def fetch_museum_enrichment(self, titles: Sequence[str]) -> list[MuseumEnrichment]:
        """Resolve Wikipedia titles to Wikidata QIDs and return enrichment data."""
        all_bindings: list[dict[str, Any]] = []
        for chunk in _chunk(titles):
            all_bindings.extend(await self._run_sparql(self._museum_query(chunk)))
        return _parse_enrichments(all_bindings)

    async def fetch_city_populations(self, city_qids: Sequence[str]) -> dict[str, list[PopulationPoint]]:
        """Fetch population time-series keyed by city QID."""
        all_bindings: list[dict[str, Any]] = []
        for chunk in _chunk(city_qids):
            all_bindings.extend(await self._run_sparql(self._population_query(chunk)))
        return parse_populations(all_bindings)

    async def _run_sparql(self, query: str) -> list[dict[str, Any]]:
        headers = {"Accept": _SPARQL_ACCEPT, "User-Agent": self._settings.user_agent}
        data: dict[str, Any] = {}
        try:
            async for attempt in retry_policy(self._settings.http_max_retries):
                with attempt:
                    response = await self._client.get(
                        str(self._settings.wikidata_sparql_url),
                        params={"query": query},
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            raise WikidataUnavailableError(f"Wikidata unreachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ExternalDataParseError(source=ExternalSource.WIKIDATA, detail=f"invalid JSON: {exc}") from exc
        try:
            return list(data["results"]["bindings"])
        except (KeyError, TypeError) as exc:
            raise ExternalDataParseError(
                source=ExternalSource.WIKIDATA, detail=f"missing results.bindings: {exc}"
            ) from exc

    def _museum_query(self, titles: list[str]) -> str:
        """Build the museum-enrichment SPARQL query.

        SECURITY NOTE: `titles` are always sourced from the MediaWiki Action API
        (via MediaWikiClient.fetch_museum_list), never user HTTP input. Quotes
        are escaped via chr(34)/chr(92) as defense-in-depth.
        """
        values = " ".join(f'"{t.replace(chr(34), chr(92) + chr(34))}"@en' for t in titles)
        return _MUSEUM_QUERY_TEMPLATE.format(values=values, city_classes=_CITY_CLASS_VALUES)

    @staticmethod
    def _population_query(qids: list[str]) -> str:
        values = " ".join(f"wd:{q}" for q in qids)
        return (
            f"SELECT ?city ?population ?year WHERE {{"
            f" VALUES ?city {{ {values} }}"
            f" ?city p:P1082 ?statement . ?statement ps:P1082 ?population . ?statement pq:P585 ?date ."
            f" BIND(YEAR(?date) AS ?year) FILTER(?year >= 2000) }}"
        )
