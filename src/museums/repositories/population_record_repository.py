"""PopulationRecord repository — bulk upsert + queries."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from museums.models.population_record import PopulationRecord


class PopulationRecordRepository:
    """Encapsulates all PopulationRecord database queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, city_id: int, records: Iterable[tuple[int, int]]) -> int:
        """Bulk upsert (year, population) pairs for a city. Returns count."""
        rows = [{"city_id": city_id, "year": year, "population": population} for year, population in records]
        if not rows:
            return 0

        stmt = (
            insert(PopulationRecord)
            .values(rows)
            .on_conflict_do_update(
                constraint="uq_population_records_city_year",
                set_={"population": insert(PopulationRecord).excluded.population},
            )
        )
        await self._session.execute(stmt)
        return len(rows)

    async def list_for_city(self, city_id: int) -> list[PopulationRecord]:
        """Return all population records for a city, ordered by year ascending."""
        result = await self._session.execute(
            select(PopulationRecord).where(PopulationRecord.city_id == city_id).order_by(PopulationRecord.year.asc())
        )
        return list(result.scalars().all())

    async def list_all_grouped(self) -> dict[int, list[PopulationRecord]]:
        """Return all population records grouped by city_id, sorted by year."""
        result = await self._session.execute(
            select(PopulationRecord).order_by(PopulationRecord.city_id, PopulationRecord.year)
        )
        records = result.scalars().all()
        grouped: dict[int, list[PopulationRecord]] = {}
        for record in records:
            grouped.setdefault(record.city_id, []).append(record)
        return grouped
