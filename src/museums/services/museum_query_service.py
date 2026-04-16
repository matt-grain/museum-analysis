"""Museum query service — thin read-only layer so routers skip direct repo access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from museums.schemas.common import PaginationMeta
from museums.schemas.museum import MuseumOut, PaginatedMuseumsOut

if TYPE_CHECKING:
    from museums.repositories.museum_repository import MuseumRepository


class MuseumQueryService:
    """Wraps MuseumRepository.list_paginated and maps results to Pydantic DTOs."""

    def __init__(self, museum_repo: MuseumRepository) -> None:
        self._museum_repo = museum_repo

    async def list_paginated(self, skip: int, limit: int) -> PaginatedMuseumsOut:
        """Return a paginated page of museums as Pydantic DTOs."""
        items, total = await self._museum_repo.list_paginated(skip=skip, limit=limit)
        return PaginatedMuseumsOut(
            items=[MuseumOut.model_validate(m) for m in items],
            pagination=PaginationMeta(total=total, skip=skip, limit=limit),
        )
