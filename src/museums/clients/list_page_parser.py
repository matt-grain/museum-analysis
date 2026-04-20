"""Pure-function parser for the Wikipedia list-of-most-visited-museums table.

Extracted from MediaWikiClient so the file stays under the 200-line limit and
so the table-shape logic is testable without any HTTP mocking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import mwparserfromhell  # type: ignore[import-untyped]  # no stubs published

_SKIP_PREFIXES = ("File:", "Image:", "Category:")

# Visitor-count patterns in the table. The cell shape varies:
#   "9,000,000 (2025)..."                    — comma-separated count
#   "3.2 million (2024)..."                  — approximate with decimal
#   "5.7 million (FY 2024-25)..."            — fiscal-year format
#   "3,751,000 (including …) (2024)..."      — number + parenthetical + year
# Parse count and year independently so all four shapes converge.
_COUNT_MILLION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*million", re.IGNORECASE)
_COUNT_THOUSANDS_RE = re.compile(r"(\d{1,3}(?:,\d{3})+)")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")

# Some City cells carry a trailing reference mark we want to drop.
_CITATION_MARKS_RE = re.compile(r"\s*\[[^\]]*\]\s*$")


@dataclass(frozen=True)
class MuseumListEntry:
    """A single museum row parsed from the Wikipedia list page.

    ``visitors_count`` / ``visitors_year`` / ``city_name`` come from the table
    cells and are used as a Wikipedia-derived fallback when Wikidata has no
    P1174 (visitors-per-year) statement for the museum.
    """

    wikipedia_title: str
    display_name: str
    visitors_count: int | None = None
    visitors_year: int | None = None
    city_name: str | None = None


def parse_list_page(wikitext: str) -> list[MuseumListEntry]:
    """Return one entry per valid museum row in the list page's wikitable."""
    tree = mwparserfromhell.parse(wikitext)
    seen: set[str] = set()
    entries: list[MuseumListEntry] = []
    for tag in tree.filter_tags():  # type: ignore[no-untyped-call]
        if str(tag.tag) != "tr":
            continue
        entry = _row_to_entry(tag)
        if entry is None:
            continue
        key = entry.wikipedia_title.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)
    return entries


def _row_to_entry(row: Any) -> MuseumListEntry | None:
    wikilinks = row.contents.filter_wikilinks()  # type: ignore[no-untyped-call]
    if not wikilinks:
        return None
    base = _wikilink_to_base(wikilinks[0])
    if base is None:
        return None

    cells = [c for c in row.contents.filter_tags() if str(c.tag) in ("td", "th")]
    visitors = _parse_visitors_cell(cells[1]) if len(cells) > 1 else None
    city = _parse_city_cell(cells[2]) if len(cells) > 2 else None
    count, year = visitors if visitors else (None, None)

    return MuseumListEntry(
        wikipedia_title=base[0],
        display_name=base[1],
        visitors_count=count,
        visitors_year=year,
        city_name=city,
    )


def _wikilink_to_base(wikilink: Any) -> tuple[str, str] | None:
    title = str(wikilink.title).strip()
    if not title or any(title.startswith(p) for p in _SKIP_PREFIXES):
        return None
    display = str(wikilink.text).strip() if wikilink.text else title
    if display.replace(",", "").replace(".", "").replace(" ", "").isdigit():
        return None
    return title, display


def _parse_visitors_cell(cell: Any) -> tuple[int, int] | None:
    text = str(cell.contents.strip_code()).strip()
    count = _parse_count(text)
    year = _parse_year(text)
    if count is None or year is None:
        return None
    return count, year


def _parse_count(text: str) -> int | None:
    """Extract a visitor count from cell text, handling both formats.

    Prefer the comma-separated form (e.g. ``3,751,000``) when present; fall
    back to the approximate ``X.Y million`` form. We check comma form first so
    a cell like ``3,751,000 (including foo)`` doesn't get mis-matched.
    """
    match = _COUNT_THOUSANDS_RE.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    match = _COUNT_MILLION_RE.search(text)
    if match:
        return int(float(match.group(1)) * 1_000_000)
    return None


def _parse_year(text: str) -> int | None:
    """First 20xx year anywhere in the text (handles "(2024)", "FY 2024-25")."""
    match = _YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def _parse_city_cell(cell: Any) -> str | None:
    text = str(cell.contents.strip_code()).strip()
    text = _CITATION_MARKS_RE.sub("", text)
    if not text:
        return None
    # Some cells list multiple locations ("Vatican City, Rome") — keep the
    # first token: it's the primary city that Wikidata is most likely to match.
    return text.split(",")[0].strip()
