"""Tests for MediaWikiClient."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from museums.clients.mediawiki_client import MediaWikiClient, MuseumListEntry
from museums.config import Settings
from museums.exceptions import MediaWikiUnavailableError

_RequestHandler = Callable[[httpx.Request], httpx.Response]

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_WIKITEXT = (_FIXTURES / "wikitext_fixture.txt").read_text(encoding="utf-8")

_MEDIAWIKI_URL = "https://en.wikipedia.org/w/api.php"


def _parse_response(wikitext: str) -> dict[str, Any]:
    return {"parse": {"wikitext": {"*": wikitext}}}


def _query_response(
    *,
    redirects: list[dict[str, str]] | None = None,
    normalized: list[dict[str, str]] | None = None,
    pages: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if redirects is not None:
        query["redirects"] = redirects
    if normalized is not None:
        query["normalized"] = normalized
    if pages is not None:
        query["pages"] = pages
    return {"query": query}


def _router(
    *,
    parse_factory: _RequestHandler,
    query_factory: _RequestHandler,
) -> _RequestHandler:
    """Route Action API requests based on the `action` query param."""

    def _side_effect(request: httpx.Request) -> httpx.Response:
        action = request.url.params.get("action")
        if action == "parse":
            return parse_factory(request)
        if action == "query":
            return query_factory(request)
        return httpx.Response(400, json={"error": f"unexpected action={action}"})

    return _side_effect


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://museums:museums@localhost:5432/museums_test",  # type: ignore[arg-type]
        http_max_retries=3,
    )


@pytest.mark.asyncio
async def test_fetch_museum_list_parses_entries_happy_path(settings: Settings) -> None:
    """fetch_museum_list returns one entry per museum wikilink in the fixture."""
    side_effect = _router(
        parse_factory=lambda _req: httpx.Response(200, json=_parse_response(_WIKITEXT)),
        query_factory=lambda _req: httpx.Response(200, json=_query_response()),
    )

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            entries = await mw.fetch_museum_list()

    titles = {e.wikipedia_title for e in entries}
    assert "Louvre" in titles
    assert "British Museum" in titles
    assert "Metropolitan Museum of Art" in titles
    assert all(isinstance(e, MuseumListEntry) for e in entries)
    assert len(entries) >= 10


@pytest.mark.asyncio
async def test_fetch_museum_list_applies_redirect_normalization(settings: Settings) -> None:
    """Redirect-source titles from the list page are replaced with canonical ones."""
    side_effect = _router(
        parse_factory=lambda _req: httpx.Response(200, json=_parse_response(_WIKITEXT)),
        query_factory=lambda _req: httpx.Response(
            200,
            json=_query_response(
                redirects=[{"from": "Louvre", "to": "Louvre Museum"}],
            ),
        ),
    )

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            entries = await mw.fetch_museum_list()

    titles = {e.wikipedia_title for e in entries}

    assert "Louvre Museum" in titles
    assert "Louvre" not in titles


@pytest.mark.asyncio
async def test_fetch_museum_list_retries_on_503_then_succeeds(settings: Settings) -> None:
    """fetch_museum_list retries on 503, succeeds on the third attempt."""
    parse_calls = 0

    def _parse(_req: httpx.Request) -> httpx.Response:
        nonlocal parse_calls
        parse_calls += 1
        if parse_calls < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_parse_response(_WIKITEXT))

    side_effect = _router(
        parse_factory=_parse,
        query_factory=lambda _req: httpx.Response(200, json=_query_response()),
    )

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(side_effect=side_effect)
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            entries = await mw.fetch_museum_list()

    assert len(entries) >= 10
    assert parse_calls == 3


@pytest.mark.asyncio
async def test_fetch_museum_list_raises_mediawiki_unavailable_after_max_retries(settings: Settings) -> None:
    """fetch_museum_list wraps exhausted retries as MediaWikiUnavailableError."""
    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(return_value=httpx.Response(503))
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            with pytest.raises(MediaWikiUnavailableError) as exc_info:
                await mw.fetch_museum_list()

    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
    assert exc_info.value.__cause__.response.status_code == 503


@pytest.mark.asyncio
async def test_normalize_titles_maps_redirects_and_normalized_and_drops_missing(settings: Settings) -> None:
    """normalize_titles applies normalization + redirects and omits missing pages."""
    payload = _query_response(
        normalized=[{"from": "louvre", "to": "Louvre"}],
        redirects=[
            {"from": "Prado Museum", "to": "Museo del Prado"},
            {"from": "Louvre", "to": "Louvre Museum"},
        ],
        pages={
            "-1": {"ns": 0, "title": "Fake Thing XZXZX", "missing": ""},
            "1": {"pageid": 1, "ns": 0, "title": "Museo del Prado"},
            "2": {"pageid": 2, "ns": 0, "title": "Louvre Museum"},
            "3": {"pageid": 3, "ns": 0, "title": "British Museum"},
        },
    )

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            mapping = await mw.normalize_titles(
                ["louvre", "Prado Museum", "British Museum", "Fake Thing XZXZX"],
            )

    assert mapping == {
        "louvre": "Louvre Museum",
        "Prado Museum": "Museo del Prado",
        "British Museum": "British Museum",
    }


@pytest.mark.asyncio
async def test_normalize_titles_chunks_large_inputs(settings: Settings) -> None:
    """normalize_titles splits >50 titles across multiple API calls."""
    titles = [f"Title_{i}" for i in range(120)]
    calls: list[list[str]] = []

    def _record(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["titles"].split("|"))
        return httpx.Response(200, json=_query_response(pages={}))

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(side_effect=_record)
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            await mw.normalize_titles(titles)

    assert [len(c) for c in calls] == [50, 50, 20]


@pytest.mark.asyncio
async def test_normalize_titles_returns_empty_for_empty_input(settings: Settings) -> None:
    """normalize_titles makes no HTTP call when given no titles."""
    with respx.mock:
        route = respx.get(_MEDIAWIKI_URL).mock(return_value=httpx.Response(500))
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            mapping = await mw.normalize_titles([])

    assert mapping == {}
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_resolve_qids_returns_wikidata_qid_via_pageprops(settings: Settings) -> None:
    """resolve_qids returns {original_title: QID} from the pageprops response."""
    payload = _query_response(
        redirects=[{"from": "Shenzhen", "to": "Shenzhen"}],  # no-op, common shape
        pages={
            "1": {
                "pageid": 1,
                "ns": 0,
                "title": "Shenzhen",
                "pageprops": {"wikibase_item": "Q15174"},
            },
            "2": {
                "pageid": 2,
                "ns": 0,
                "title": "Beijing",
                "pageprops": {"wikibase_item": "Q956"},
            },
            "-1": {"ns": 0, "title": "Not a real place", "missing": ""},
        },
    )

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            mapping = await mw.resolve_qids(["Shenzhen", "Beijing", "Not a real place"])

    assert mapping == {"Shenzhen": "Q15174", "Beijing": "Q956"}


@pytest.mark.asyncio
async def test_resolve_qids_follows_redirect_chain(settings: Settings) -> None:
    """resolve_qids walks normalized+redirects to the page carrying the QID."""
    payload = _query_response(
        redirects=[{"from": "City of London", "to": "London"}],
        pages={"1": {"title": "London", "pageprops": {"wikibase_item": "Q84"}}},
    )

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(return_value=httpx.Response(200, json=payload))
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            mapping = await mw.resolve_qids(["City of London"])

    assert mapping == {"City of London": "Q84"}
