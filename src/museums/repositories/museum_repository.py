"""Museum repository — CRUD + upsert + paginated list."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from museums.models.museum import Museum

_MUSEUM_UPSERT_FIELDS = ("wikipedia_title", "wikidata_qid", "city_id", "country")


class MuseumRepository:
    """Encapsulates all Museum database queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name(self, name: str) -> Museum | None:
        """Return a Museum by name, or None if not found."""
        result = await self._session.execute(select(Museum).where(Museum.name == name))
        return result.scalar_one_or_none()

    async def list_paginated(self, skip: int, limit: int) -> tuple[list[Museum], int]:
        """Return (items, total) with eager-loaded city and visitor_records."""
        total_result = await self._session.execute(select(func.count()).select_from(Museum))
        total = total_result.scalar_one()
        items_result = await self._session.execute(
            select(Museum)
            .options(joinedload(Museum.city), selectinload(Museum.visitor_records))
            .offset(skip)
            .limit(limit)
            .order_by(Museum.name)
        )
        return list(items_result.unique().scalars().all()), total

    async def upsert_by_name(
        self,
        name: str,
        wikipedia_title: str,
        wikidata_qid: str | None,
        city_id: int | None,
        country: str | None,
    ) -> Museum:
        """Insert or update a museum by name. Returns the persisted row."""
        values = {
            "name": name,
            "wikipedia_title": wikipedia_title,
            "wikidata_qid": wikidata_qid,
            "city_id": city_id,
            "country": country,
        }
        stmt = (
            insert(Museum)
            .values(**values)
            .on_conflict_do_update(index_elements=["name"], set_={k: values[k] for k in _MUSEUM_UPSERT_FIELDS})
            .returning(Museum)
        )
        result = await self._session.execute(stmt)
        row: Museum = result.scalar_one()
        # ON CONFLICT DO UPDATE bypasses SQLAlchemy's identity map; on a second
        # upsert within the same session, .returning() gives the updated row
        # but attributes like updated_at remain stale. refresh() re-reads the row.
        await self._session.refresh(row)
        return row

    async def delete_all(self) -> None:
        """Delete all museum rows (used for full-wipe refresh if needed)."""
        await self._session.execute(delete(Museum))
