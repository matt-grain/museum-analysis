"""Tests for the pure-function Wikipedia list-page parser."""

from __future__ import annotations

from museums.clients.list_page_parser import parse_list_page

_TWO_ROW_WIKITEXT = """
{| class="wikitable sortable"
! Name !! Visitors !! City !! Country
|-
| [[Louvre]] || 9,000,000 (2025) || Paris || {{flag|France}}
|-
| [[Shenzhen Museum]] || 6,805,000 (2024)AECOM Survey || Shenzhen || {{flag|China}}
|-
| [[File:Flag_of_Foo.svg]] || 1,000,000 (2000) || Nowhere ||
|}
"""


def test_parse_list_page_extracts_visitors_year_and_city() -> None:
    """Visitor count, year, and city are read from the table cells."""
    entries = parse_list_page(_TWO_ROW_WIKITEXT)

    titles = [e.wikipedia_title for e in entries]
    assert "Louvre" in titles
    assert "Shenzhen Museum" in titles

    louvre = next(e for e in entries if e.wikipedia_title == "Louvre")

    assert louvre.visitors_count == 9_000_000
    assert louvre.visitors_year == 2025
    assert louvre.city_name == "Paris"

    shenzhen = next(e for e in entries if e.wikipedia_title == "Shenzhen Museum")

    assert shenzhen.visitors_count == 6_805_000
    assert shenzhen.visitors_year == 2024
    assert shenzhen.city_name == "Shenzhen"


def test_parse_list_page_skips_file_wikilinks() -> None:
    """Rows whose first wikilink is a File: / Image: / Category: entry are ignored."""
    entries = parse_list_page(_TWO_ROW_WIKITEXT)

    titles = {e.wikipedia_title for e in entries}

    assert not any(t.startswith("File:") for t in titles)


def test_parse_list_page_returns_none_fields_when_cells_are_malformed() -> None:
    """Rows without a parseable visitor cell still return an entry with None fields."""
    malformed = """
    {| class="wikitable"
    ! Name !! Visitors !! City
    |-
    | [[Ghost Museum]] || n/a || Somewhere
    |}
    """

    entries = parse_list_page(malformed)

    assert len(entries) == 1
    assert entries[0].wikipedia_title == "Ghost Museum"
    assert entries[0].visitors_count is None
    assert entries[0].visitors_year is None
    assert entries[0].city_name == "Somewhere"


def test_parse_list_page_handles_x_point_y_million_format() -> None:
    """Cells like "3.2 million (2024)" parse to 3_200_000 + 2024."""
    wikitext = """
    {| class="wikitable"
    ! Name !! Visitors !! City
    |-
    | [[Musée National d'Histoire Naturelle]] || 3.2 million (2024) || Paris
    |-
    | [[M+]] || 2.61 million (2024) || Hong Kong
    |}
    """

    entries = parse_list_page(wikitext)

    mnhn = next(e for e in entries if "Histoire" in e.wikipedia_title)
    m_plus = next(e for e in entries if e.wikipedia_title == "M+")

    assert mnhn.visitors_count == 3_200_000
    assert mnhn.visitors_year == 2024
    assert m_plus.visitors_count == 2_610_000
    assert m_plus.visitors_year == 2024


def test_parse_list_page_handles_fiscal_year_and_parenthetical_text() -> None:
    """Cells with "FY 2024-25" and "(including foo) (2024)" still parse."""
    wikitext = """
    {| class="wikitable"
    ! Name !! Visitors !! City
    |-
    | [[Metropolitan Museum of Art]] || 5.7 million (FY 2024-25) || New York City
    |-
    | [[Musée d'Orsay]] || 3,751,000 (including Musée de l'Orangerie) (2024) || Paris
    |}
    """

    entries = parse_list_page(wikitext)

    met = next(e for e in entries if e.wikipedia_title == "Metropolitan Museum of Art")
    orsay = next(e for e in entries if "Orsay" in e.wikipedia_title)

    assert met.visitors_count == 5_700_000
    assert met.visitors_year == 2024
    assert orsay.visitors_count == 3_751_000
    assert orsay.visitors_year == 2024


def test_parse_list_page_takes_first_city_for_comma_separated_cells() -> None:
    """A cell like "Vatican City, Rome" keeps only the first city for Wikidata lookup."""
    wikitext = """
    {| class="wikitable"
    ! Name !! Visitors !! City
    |-
    | [[Vatican Museums]] || 6,825,436 (2024) || Vatican City, Rome
    |}
    """

    entries = parse_list_page(wikitext)

    assert entries[0].city_name == "Vatican City"
