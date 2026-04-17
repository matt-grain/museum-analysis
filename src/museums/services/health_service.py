"""HealthService — delegates the DB liveness check to HealthRepository."""

from __future__ import annotations

from museums.repositories.health_repository import HealthRepository


class HealthService:
    """Exposes a check() method that verifies database connectivity."""

    def __init__(self, repo: HealthRepository) -> None:
        self._repo = repo

    async def check(self) -> None:
        """Raise an exception if the database is unreachable."""
        await self._repo.ping()
