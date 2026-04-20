"""Async factory functions for building test fixtures."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from museums.clients.mediawiki_client import MuseumListEntry
from museums.clients.population_parsing import PopulationPoint
from museums.clients.wikidata_client import MuseumEnrichment, VisitorPoint
from museums.models.city import City
from museums.models.museum import Museum
from museums.models.population_record import PopulationRecord
from museums.models.visitor_record import VisitorRecord


async def build_city(
    session: AsyncSession,
    *,
    qid: str = "Q90",
    name: str = "Paris",
    country: str = "France",
) -> City:
    """Insert a City and return the flushed row with id populated."""
    city = City(wikidata_qid=qid, name=name, country=country)
    session.add(city)
    await session.flush()
    return city


async def build_museum(
    session: AsyncSession,
    *,
    name: str = "Louvre",
    wikipedia_title: str = "Louvre",
    city: City | None = None,
    qid: str | None = "Q19675",
) -> Museum:
    """Insert a Museum and return the flushed row with id populated."""
    museum = Museum(
        name=name,
        wikipedia_title=wikipedia_title,
        wikidata_qid=qid,
        city_id=city.id if city is not None else None,
        country=city.country if city is not None else None,
    )
    session.add(museum)
    await session.flush()
    return museum


async def build_visitor_record(
    session: AsyncSession,
    *,
    museum: Museum,
    year: int = 2023,
    visitors: int = 8_900_000,
) -> VisitorRecord:
    """Insert a VisitorRecord and return the flushed row with id populated."""
    record = VisitorRecord(museum_id=museum.id, year=year, visitors=visitors)
    session.add(record)
    await session.flush()
    return record


async def build_population_record(
    session: AsyncSession,
    *,
    city: City,
    year: int = 2023,
    population: int = 2_100_000,
) -> PopulationRecord:
    """Insert a PopulationRecord and return the flushed row with id populated."""
    record = PopulationRecord(city_id=city.id, year=year, population=population)
    session.add(record)
    await session.flush()
    return record


def make_museum_list_entry(
    title: str = "Louvre",
    display_name: str | None = None,
    visitors_count: int | None = 8_900_000,
    visitors_year: int | None = 2023,
) -> MuseumListEntry:
    """Build a MuseumListEntry without touching the database.

    Default ``visitors_count`` is well above ``Settings.museum_visitor_threshold``
    so entries survive the ingestion workflow's Wikipedia-side threshold filter.
    """
    return MuseumListEntry(
        wikipedia_title=title,
        display_name=display_name or title,
        visitors_count=visitors_count,
        visitors_year=visitors_year,
    )


def make_museum_enrichment(
    title: str = "Louvre",
    museum_qid: str = "Q19675",
    museum_label: str = "Louvre Museum",
    city_qid: str | None = "Q90",
    city_label: str | None = "Paris",
    country_label: str | None = "France",
    visitors: int = 8_900_000,
    year: int = 2019,
) -> MuseumEnrichment:
    """Build a MuseumEnrichment without touching the database."""
    return MuseumEnrichment(
        wikipedia_title=title,
        museum_qid=museum_qid,
        museum_label=museum_label,
        city_qid=city_qid,
        city_label=city_label,
        country_label=country_label,
        visitor_records=[VisitorPoint(year=year, visitors=visitors)],
    )


def make_population_series(
    start_year: int = 2010,
    n: int = 5,
    base: int = 2_000_000,
    step: int = 50_000,
) -> list[PopulationPoint]:
    """Build a list of PopulationPoints without touching the database."""
    return [PopulationPoint(year=start_year + i, population=base + i * step) for i in range(n)]
