"""Cities router — city population history."""

from __future__ import annotations

from fastapi import APIRouter, status

from museums.dependencies import CityQueryServiceDep
from museums.schemas.city import CityPopulationsOut

router = APIRouter(prefix="/cities", tags=["cities"])


@router.get(
    "/populations",
    response_model=list[CityPopulationsOut],
    status_code=status.HTTP_200_OK,
)
async def list_city_populations(service: CityQueryServiceDep) -> list[CityPopulationsOut]:
    """Return all cities with their full population history."""
    return await service.list_with_populations()
