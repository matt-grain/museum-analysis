"""HealthRepository — DB liveness check."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HealthRepository:
    """Encapsulates the database liveness probe query."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ping(self) -> None:
        """Execute SELECT 1 to verify the database connection is alive."""
        await self._session.execute(text("SELECT 1"))
