"""Async factory functions for building test fixtures."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

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
