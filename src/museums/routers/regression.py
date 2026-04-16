"""Regression result router."""

from __future__ import annotations

from fastapi import APIRouter, status

from museums.dependencies import RegressionServiceDep
from museums.schemas.regression import RegressionResultOut

router = APIRouter(prefix="/regression", tags=["regression"])


@router.get("", response_model=RegressionResultOut, status_code=status.HTTP_200_OK)
async def get_regression(service: RegressionServiceDep) -> RegressionResultOut:
    """Fit a log-log regression model and return results. Returns 422 if <5 rows."""
    result = await service.fit()
    return RegressionResultOut.model_validate(result, from_attributes=True)
