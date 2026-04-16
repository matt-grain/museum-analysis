"""Harmonized data router."""

from __future__ import annotations

from fastapi import APIRouter, status

from museums.dependencies import HarmonizationServiceDep
from museums.schemas.harmonized import HarmonizedRowOut

router = APIRouter(prefix="/harmonized", tags=["harmonized"])


@router.get("", response_model=list[HarmonizedRowOut], status_code=status.HTTP_200_OK)
async def get_harmonized(service: HarmonizationServiceDep) -> list[HarmonizedRowOut]:
    """Return all harmonized museum/population rows computed on demand."""
    rows = await service.build_harmonized_rows()
    return [HarmonizedRowOut.model_validate(r, from_attributes=True) for r in rows]
