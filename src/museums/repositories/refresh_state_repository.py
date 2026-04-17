"""RefreshState repository — read/write the singleton refresh tracking row."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from museums.models.refresh_state import RefreshState


class RefreshStateRepository:
    """Encapsulates all RefreshState database queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> RefreshState:
        """Return the singleton row, auto-creating it if absent."""
        result = await self._session.execute(select(RefreshState).where(RefreshState.id == 1))
        state = result.scalar_one_or_none()
        if state is None:
            state = RefreshState(id=1)
            self._session.add(state)
        return state

    async def mark_refreshed(self, museums: int, cities: int) -> RefreshState:
        """Update last_refresh_at and counts. Returns the updated row."""
        now = datetime.now(UTC)
        await self._session.execute(
            update(RefreshState)
            .where(RefreshState.id == 1)
            .values(
                last_refresh_at=now,
                last_refresh_museums_count=museums,
                last_refresh_cities_count=cities,
            )
        )
        return await self.get()
