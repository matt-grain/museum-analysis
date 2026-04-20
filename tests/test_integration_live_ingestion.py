"""Live integration test — hits Wikipedia + Wikidata and asserts 42+ museums.

Run explicitly::

    uv run pytest -m integration

Skipped by default (see ``[tool.pytest.ini_options]`` addopts in pyproject.toml).
This test is the reference for the project's coverage claim against the
Wikipedia "List of most-visited museums" article (42 rows with >2M visitors
in 2024 at the time the test was written).
"""

from __future__ import annotations

import sys

import httpx
import pytest
import structlog

from museums.clients.mediawiki_client import MediaWikiClient
from museums.clients.wikidata_client import WikidataClient
from museums.config import Settings
from museums.workflows.fallback_enrichment import merge_enrichments

_EXPECTED_MIN_COUNT = 42
_VISITOR_THRESHOLD = 2_000_000

# A subset of museums that exercise each recovery path:
#   - redirect normalization (Prado Museum -> Museo del Prado)
#   - London urban-agglomeration class (British Museum)
#   - Wikipedia-derived fallback (Shenzhen Museum — no P1174 on Wikidata)
#   - Mexico / non-English metadata (National Museum of Anthropology)
_SPOT_CHECK_TITLES = [
    "Louvre Museum",
    "British Museum",
    "Museo del Prado",
    "Shenzhen Museum",
    "Nanjing Museum",
    "Hubei Provincial Museum",
    "National Museum of Anthropology",
    "Uffizi",
]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_ingestion_covers_at_least_42_museums() -> None:
    """End-to-end: MediaWiki + Wikidata + fallback yields >= 42 enriched museums."""
    # Arrange
    settings = Settings(
        database_url="postgresql+asyncpg://museums:museums@localhost:5432/museums",  # type: ignore[arg-type]
        user_agent="MuseumsIntegrationTest/0.1 (homework@ivado-labs)",
    )
    log = structlog.get_logger("integration-test")

    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        mediawiki = MediaWikiClient(client, settings)
        wikidata = WikidataClient(client, settings)

        # Act — mirror IngestionWorkflow._fetch_data
        entries = await mediawiki.fetch_museum_list()
        filtered = [e for e in entries if e.visitors_count is not None and e.visitors_count > _VISITOR_THRESHOLD]
        wd_enrichments = await wikidata.fetch_museum_enrichment([e.wikipedia_title for e in filtered])
        merged = await merge_enrichments(filtered, wd_enrichments, mediawiki, log)

    # Assert — overall coverage
    titles_lower = {e.wikipedia_title.lower() for e in merged}
    labels_lower = {e.museum_label.lower() for e in merged}
    haystack = titles_lower | labels_lower

    sys.stdout.write(
        f"\n=== ingestion coverage: {len(merged)} museums "
        f"(source of truth: Wikipedia with >{_VISITOR_THRESHOLD:,} visitors) ===\n"
    )
    for e in sorted(merged, key=lambda x: x.museum_label.lower()):
        records_summary = f"{len(e.visitor_records)} visitor record(s)" if e.visitor_records else "NO visitor records"
        sys.stdout.write(f"  {e.museum_label}  [{records_summary}]\n")

    assert len(merged) == _EXPECTED_MIN_COUNT, (
        f"expected exactly {_EXPECTED_MIN_COUNT} museums (Wikipedia source of truth), got {len(merged)}"
    )

    # Every merged museum must have at least one visitor record — either from
    # Wikidata P1174 or from the Wikipedia fallback cell.
    no_visitors = [e.museum_label for e in merged if not e.visitor_records]
    assert not no_visitors, f"museums without any visitor record: {no_visitors}"

    # Assert — spot-check that the hard cases are present
    missing = [t for t in _SPOT_CHECK_TITLES if not any(t.lower() in h for h in haystack)]
    assert not missing, f"spot-check failed — missing: {missing}"
