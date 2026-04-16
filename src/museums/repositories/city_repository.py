"""City repository — CRUD + upsert operations."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from museums.models.city import City


class CityRepository:
    """Encapsulates all City database queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_qid(self, qid: str) -> City | None:
        """Return a City by Wikidata QID, or None if not found."""
        result = await self._session.execute(select(City).where(City.wikidata_qid == qid))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[City]:
        """Return all cities ordered by name."""
        result = await self._session.execute(select(City).order_by(City.name))
        return list(result.scalars().all())

    async def delete_all(self) -> None:
        """Delete all cities. CASCADEs to population_records; nullifies museums.city_id."""
        await self._session.execute(delete(City))

    async def upsert_by_qid(self, qid: str, name: str, country: str | None) -> City:
        """Insert or update a city by Wikidata QID. Returns the persisted row."""
        stmt = (
            insert(City)
            .values(wikidata_qid=qid, name=name, country=country)
            .on_conflict_do_update(
                index_elements=["wikidata_qid"],
                set_={"name": name, "country": country},
            )
            .returning(City)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()
