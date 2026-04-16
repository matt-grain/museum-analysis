"""Tests for MediaWikiClient."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from museums.clients.mediawiki_client import MediaWikiClient, MuseumListEntry
from museums.config import Settings
from museums.exceptions import MediaWikiUnavailableError

_FIXTURES = Path(__file__).parent.parent / "fixtures"
_WIKITEXT = (_FIXTURES / "wikitext_fixture.txt").read_text(encoding="utf-8")

_MEDIAWIKI_URL = "https://en.wikipedia.org/w/api.php"


def _action_api_response(wikitext: str) -> dict[object, object]:
    return {"parse": {"wikitext": {"*": wikitext}}}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://museums:museums@localhost:5432/museums_test",  # type: ignore[arg-type]
        http_max_retries=3,
    )


@pytest.mark.asyncio
async def test_fetch_museum_list_parses_entries_happy_path(settings: Settings) -> None:
    """fetch_museum_list returns one entry per museum wikilink in the fixture."""
    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(return_value=httpx.Response(200, json=_action_api_response(_WIKITEXT)))
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
async def test_fetch_museum_list_retries_on_503_then_succeeds(settings: Settings) -> None:
    """fetch_museum_list retries on 503, succeeds on the third attempt."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_action_api_response(_WIKITEXT))

    with respx.mock:
        respx.get(_MEDIAWIKI_URL).mock(side_effect=_side_effect)
        async with httpx.AsyncClient() as client:
            mw = MediaWikiClient(client, settings)
            entries = await mw.fetch_museum_list()

    assert len(entries) >= 10
    assert call_count == 3


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
