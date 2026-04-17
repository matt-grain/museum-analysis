"""MediaWiki client — fetches the canonical museum list via Action API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
import mwparserfromhell  # type: ignore[import-untyped]  # no stubs published

from museums.config import Settings
from museums.enums.external_source import ExternalSource
from museums.exceptions import ExternalDataParseError, MediaWikiUnavailableError
from museums.http_client import retry_policy

_MIN_EXPECTED_ENTRIES = 10
_SKIP_PREFIXES = ("File:", "Image:", "Category:")


@dataclass(frozen=True)
class MuseumListEntry:
    """A single museum entry parsed from the Wikipedia list page."""

    wikipedia_title: str
    display_name: str


def _extract_wikitext(data: dict[str, Any]) -> str:
    """Pull wikitext string out of a MediaWiki API JSON response."""
    try:
        return str(data["parse"]["wikitext"]["*"])
    except (KeyError, TypeError) as exc:
        raise ExternalDataParseError(
            source=ExternalSource.MEDIAWIKI,
            detail=f"missing parse.wikitext.*: {exc}",
        ) from exc


def _wikilink_to_entry(wikilink: Any) -> MuseumListEntry | None:
    """Convert one mwparserfromhell Wikilink node into a MuseumListEntry, or None."""
    # wikilink is mwparserfromhell.nodes.Wikilink — untyped third-party lib
    title = str(wikilink.title).strip()
    display = str(wikilink.text).strip() if wikilink.text else title
    if any(title.startswith(p) for p in _SKIP_PREFIXES):
        return None
    if display.replace(",", "").replace(".", "").replace(" ", "").isdigit():
        return None
    return MuseumListEntry(wikipedia_title=title, display_name=display) if title else None


class MediaWikiClient:
    """Fetches the canonical museum list from the Wikipedia Action API."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def fetch_museum_list(self) -> list[MuseumListEntry]:
        """Return all museum entries from the Wikipedia list page.

        Raises:
            MediaWikiUnavailableError: on HTTP failure after max retries.
            ExternalDataParseError: on unexpected response shape or empty result.
        """
        wikitext = await self._fetch_wikitext()
        return self._parse_entries(wikitext)

    async def _fetch_wikitext(self) -> str:
        params = {
            "action": "parse",
            "page": self._settings.wikipedia_list_page_title,
            "format": "json",
            "prop": "wikitext",
            "redirects": "1",
        }
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
        return _extract_wikitext(data)

    def _parse_entries(self, wikitext: str) -> list[MuseumListEntry]:
        tree = mwparserfromhell.parse(wikitext)
        seen: set[str] = set()
        entries: list[MuseumListEntry] = []
        for tag in tree.filter_tags():  # type: ignore[no-untyped-call]
            if str(tag.tag) != "tr":
                continue
            wikilinks = tag.contents.filter_wikilinks()  # type: ignore[no-untyped-call]
            if not wikilinks:
                continue
            entry = _wikilink_to_entry(wikilinks[0])
            if entry is None:
                continue
            key = entry.wikipedia_title.lower().strip()
            if key not in seen:
                seen.add(key)
                entries.append(entry)
        if len(entries) < _MIN_EXPECTED_ENTRIES:
            raise ExternalDataParseError(
                source=ExternalSource.MEDIAWIKI,
                detail=f"only {len(entries)} entries parsed — page layout may have changed",
            )
        return entries
