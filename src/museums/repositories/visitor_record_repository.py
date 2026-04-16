"""VisitorRecord repository — bulk upsert + queries."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from museums.models.visitor_record import VisitorRecord


class VisitorRecordRepository:
    """Encapsulates all VisitorRecord database queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(self, museum_id: int, records: Iterable[tuple[int, int]]) -> int:
        """Bulk upsert (year, visitors) pairs for a museum. Returns count."""
        rows = [{"museum_id": museum_id, "year": year, "visitors": visitors} for year, visitors in records]
        if not rows:
            return 0

        stmt = (
            insert(VisitorRecord)
            .values(rows)
            .on_conflict_do_update(
                constraint="uq_visitor_records_museum_year",
                set_={"visitors": insert(VisitorRecord).excluded.visitors},
            )
        )
        await self._session.execute(stmt)
        return len(rows)

    async def list_for_museum(self, museum_id: int) -> list[VisitorRecord]:
        """Return all visitor records for a museum, ordered by year descending."""
        result = await self._session.execute(
            select(VisitorRecord).where(VisitorRecord.museum_id == museum_id).order_by(VisitorRecord.year.desc())
        )
        return list(result.scalars().all())
