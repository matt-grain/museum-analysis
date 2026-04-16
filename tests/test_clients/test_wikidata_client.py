"""Tests for WikidataClient."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from museums.clients.population_parsing import PopulationPoint, filter_scope_outliers
from museums.clients.wikidata_client import MuseumEnrichment, WikidataClient
from museums.config import Settings
from museums.exceptions import ExternalDataParseError

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_ENRICHMENT_JSON = json.loads((_FIXTURES / "wikidata_museum_enrichment.json").read_text(encoding="utf-8"))
_POPULATIONS_JSON = json.loads((_FIXTURES / "wikidata_city_populations.json").read_text(encoding="utf-8"))

_SPARQL_URL = "https://query.wikidata.org/sparql"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://museums:museums@localhost:5432/museums_test",  # type: ignore[arg-type]
        http_max_retries=3,
    )


@pytest.mark.asyncio
async def test_fetch_museum_enrichment_parses_sparql_results(settings: Settings) -> None:
    """fetch_museum_enrichment builds MuseumEnrichment objects from SPARQL bindings."""
    with respx.mock:
        respx.get(_SPARQL_URL).mock(return_value=httpx.Response(200, json=_ENRICHMENT_JSON))
        async with httpx.AsyncClient() as client:
            wd = WikidataClient(client, settings)
            enrichments = await wd.fetch_museum_enrichment(["Louvre", "British Museum"])

    assert len(enrichments) == 2

    louvre = next(e for e in enrichments if e.wikipedia_title == "Louvre")
    assert isinstance(louvre, MuseumEnrichment)
    assert louvre.museum_qid == "Q19675"
    assert louvre.city_qid == "Q90"
    assert louvre.country_label == "France"
    assert len(louvre.visitor_records) == 2
    years = [vp.year for vp in louvre.visitor_records]
    assert years == sorted(years)

    british = next(e for e in enrichments if e.wikipedia_title == "British Museum")
    assert british.museum_qid == "Q6373"
    assert british.city_qid == "Q84"
    assert len(british.visitor_records) == 2


@pytest.mark.asyncio
async def test_fetch_city_populations_groups_by_qid(settings: Settings) -> None:
    """fetch_city_populations groups rows by QID with sorted PopulationPoint lists."""
    with respx.mock:
        respx.get(_SPARQL_URL).mock(return_value=httpx.Response(200, json=_POPULATIONS_JSON))
        async with httpx.AsyncClient() as client:
            wd = WikidataClient(client, settings)
            populations = await wd.fetch_city_populations(["Q90", "Q84"])

    assert len(populations) == 2
    assert "Q90" in populations
    assert "Q84" in populations

    paris = populations["Q90"]
    assert len(paris) == 2
    assert all(isinstance(p, PopulationPoint) for p in paris)
    assert paris[0].year < paris[1].year

    london = populations["Q84"]
    assert len(london) == 2
    assert london[0].year < london[1].year


@pytest.mark.asyncio
async def test_fetch_raises_external_data_parse_error_on_missing_bindings(settings: Settings) -> None:
    """fetch_museum_enrichment raises ExternalDataParseError when results.bindings is absent."""
    bad_response: dict[str, object] = {"results": {}}

    with respx.mock:
        respx.get(_SPARQL_URL).mock(return_value=httpx.Response(200, json=bad_response))
        async with httpx.AsyncClient() as client:
            wd = WikidataClient(client, settings)
            with pytest.raises(ExternalDataParseError) as exc_info:
                await wd.fetch_museum_enrichment(["Louvre"])

    assert exc_info.value.source == "wikidata"


def test_filter_scope_outliers_drops_metro_when_minority_mixed_in() -> None:
    """A lone metro-area value among admin-boundary values is filtered out."""
    raw = {2005: 12_600_000, 2010: 13_100_000, 2015: 13_600_000, 2016: 38_000_000, 2020: 14_100_000}

    filtered = filter_scope_outliers(raw)

    assert 2016 not in filtered
    assert set(filtered.keys()) == {2005, 2010, 2015, 2020}


def test_filter_scope_outliers_drops_metro_when_majority_mixed_in() -> None:
    """Even when metro values dominate the series, we anchor on the min and drop values >2x."""
    # 3 metro values, 1 admin value — median would pick metro; MIN-anchored filter keeps admin
    raw = {2005: 13_000_000, 2010: 38_000_000, 2015: 38_500_000, 2020: 39_000_000}

    filtered = filter_scope_outliers(raw)

    assert set(filtered.keys()) == {2005}


def test_filter_scope_outliers_keeps_internally_consistent_series() -> None:
    """A series where max/min <= 2x is treated as internally consistent — no filtering."""
    raw = {2000: 8_000_000, 2010: 8_400_000, 2020: 8_800_000}

    filtered = filter_scope_outliers(raw)

    assert filtered == raw


def test_filter_scope_outliers_skips_when_fewer_than_three_points() -> None:
    """Outlier filter needs >=3 points; otherwise pass through."""
    raw = {2015: 13_600_000, 2016: 38_000_000}

    filtered = filter_scope_outliers(raw)

    assert filtered == raw
