"""MediaWiki client — fetches the canonical museum list via Action API."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from museums.clients.list_page_parser import MuseumListEntry, parse_list_page
from museums.config import Settings
from museums.enums.external_source import ExternalSource
from museums.exceptions import ExternalDataParseError, MediaWikiUnavailableError
from museums.http_client import retry_policy

__all__ = ["MediaWikiClient", "MuseumListEntry"]
_MIN_EXPECTED_ENTRIES = 10
_TITLES_CHUNK_SIZE = 50  # MediaWiki titles= limit for non-bot clients


def _chunk[T](seq: Sequence[T], size: int) -> Iterator[list[T]]:
    """Yield successive fixed-size chunks from seq."""
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def _resolve_title_mapping(originals: Sequence[str], data: dict[str, Any]) -> dict[str, str]:
    """Walk ``normalized`` then ``redirects`` arrays to map original -> canonical.

    Missing pages are omitted from the result so callers keep the original and
    let downstream SPARQL drop them silently.
    """
    query: dict[str, Any] = data.get("query") or {}
    normalized_rows: list[dict[str, str]] = query.get("normalized") or []
    redirect_rows: list[dict[str, str]] = query.get("redirects") or []
    pages: dict[str, dict[str, Any]] = query.get("pages") or {}
    normalized = {row["from"]: row["to"] for row in normalized_rows}
    redirects = {row["from"]: row["to"] for row in redirect_rows}
    missing_titles = {str(p["title"]) for p in pages.values() if "missing" in p}
    mapping: dict[str, str] = {}
    for original in originals:
        current = normalized.get(original, original)
        current = redirects.get(current, current)
        if current in missing_titles:
            continue
        mapping[original] = current
    return mapping


def _resolve_qid_mapping(originals: Sequence[str], data: dict[str, Any]) -> dict[str, str]:
    """Map each original title to its Wikidata QID via the ``pageprops`` response.

    Applies ``normalized`` + ``redirects`` so inputs like "Shenzhen" walk to the
    canonical page and pick up ``pageprops.wikibase_item``. Titles without a
    Wikidata link or that are missing are omitted.
    """
    query: dict[str, Any] = data.get("query") or {}
    pages: dict[str, dict[str, Any]] = query.get("pages") or {}
    normalized_rows: list[dict[str, str]] = query.get("normalized") or []
    redirect_rows: list[dict[str, str]] = query.get("redirects") or []
    canonical_to_qid: dict[str, str] = {}
    for page in pages.values():
        title = page.get("title")
        props: dict[str, Any] = page.get("pageprops") or {}
        qid = props.get("wikibase_item")
        if isinstance(title, str) and isinstance(qid, str):
            canonical_to_qid[title] = qid
    normalized = {row["from"]: row["to"] for row in normalized_rows}
    redirects = {row["from"]: row["to"] for row in redirect_rows}
    mapping: dict[str, str] = {}
    for original in originals:
        current = normalized.get(original, original)
        current = redirects.get(current, current)
        qid = canonical_to_qid.get(current)
        if qid is not None:
            mapping[original] = qid
    return mapping


def _with_canonical_title(entry: MuseumListEntry, canonical: dict[str, str]) -> MuseumListEntry:
    """Rewrite an entry's ``wikipedia_title`` using the canonical mapping."""
    return MuseumListEntry(
        wikipedia_title=canonical.get(entry.wikipedia_title, entry.wikipedia_title),
        display_name=entry.display_name,
        visitors_count=entry.visitors_count,
        visitors_year=entry.visitors_year,
        city_name=entry.city_name,
    )


def _extract_wikitext(data: dict[str, Any]) -> str:
    """Pull wikitext string out of a MediaWiki API JSON response."""
    try:
        return str(data["parse"]["wikitext"]["*"])
    except (KeyError, TypeError) as exc:
        raise ExternalDataParseError(
            source=ExternalSource.MEDIAWIKI,
            detail=f"missing parse.wikitext.*: {exc}",
        ) from exc


class MediaWikiClient:
    """Fetches the canonical museum list from the Wikipedia Action API."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def fetch_museum_list(self) -> list[MuseumListEntry]:
        """Return all museum entries from the Wikipedia list page.

        Titles are normalized via the Action API so redirect-source names in the
        list page (e.g. "Prado Museum") become canonical Wikipedia titles
        (e.g. "Museo del Prado"); Wikidata SPARQL matches ``schema:name`` only
        against the canonical, so skipping this step silently drops redirects.

        Each entry also carries optional visitor/city fields scraped from the
        table cells, used as a fallback when Wikidata has no P1174 statement.

        Raises:
            MediaWikiUnavailableError: on HTTP failure after max retries.
            ExternalDataParseError: on unexpected response shape or empty result.
        """
        wikitext = await self._fetch_wikitext()
        raw_entries = parse_list_page(wikitext)
        if len(raw_entries) < _MIN_EXPECTED_ENTRIES:
            raise ExternalDataParseError(
                source=ExternalSource.MEDIAWIKI,
                detail=f"only {len(raw_entries)} entries parsed — page layout may have changed",
            )
        canonical = await self.normalize_titles([e.wikipedia_title for e in raw_entries])
        return [_with_canonical_title(e, canonical) for e in raw_entries]

    async def normalize_titles(self, titles: Sequence[str]) -> dict[str, str]:
        """Resolve each title to its canonical Wikipedia article name.

        Applies both title normalization (whitespace/case) and page redirects.
        Titles that don't exist are omitted from the mapping.
        """
        mapping: dict[str, str] = {}
        for chunk in _chunk(titles, _TITLES_CHUNK_SIZE):
            data = await self._get_action_api(
                {"action": "query", "format": "json", "redirects": "1", "titles": "|".join(chunk)}
            )
            mapping.update(_resolve_title_mapping(chunk, data))
        return mapping

    async def resolve_qids(self, titles: Sequence[str]) -> dict[str, str]:
        """Resolve each title to its Wikidata QID via ``pageprops``.

        Returns ``{original_title: QID}``. Titles with no Wikipedia article or
        no linked Wikidata item are omitted. Used to look up Wikidata QIDs for
        cities scraped from the list page (needed to fetch P1082 population).
        """
        mapping: dict[str, str] = {}
        for chunk in _chunk(titles, _TITLES_CHUNK_SIZE):
            data = await self._get_action_api(
                {
                    "action": "query",
                    "format": "json",
                    "redirects": "1",
                    "prop": "pageprops",
                    "ppprop": "wikibase_item",
                    "titles": "|".join(chunk),
                }
            )
            mapping.update(_resolve_qid_mapping(chunk, data))
        return mapping

    async def _fetch_wikitext(self) -> str:
        data = await self._get_action_api(
            {
                "action": "parse",
                "page": self._settings.wikipedia_list_page_title,
                "format": "json",
                "prop": "wikitext",
                "redirects": "1",
            }
        )
        return _extract_wikitext(data)

    async def _get_action_api(self, params: dict[str, str]) -> dict[str, Any]:
        """GET the MediaWiki Action API with retry + unified error mapping."""
        data: dict[str, Any] = {}
        try:
            async for attempt in retry_policy(self._settings.http_max_retries):
                with attempt:
                    response = await self._client.get(
                        str(self._settings.mediawiki_base_url),
                        params=params,
                        headers={"User-Agent": self._settings.user_agent},
                    )
                    response.raise_for_status()
                    data = response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            raise MediaWikiUnavailableError(f"MediaWiki unreachable: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ExternalDataParseError(source=ExternalSource.MEDIAWIKI, detail=f"invalid JSON: {exc}") from exc
        return data
