"""Regression result router."""

from __future__ import annotations

from fastapi import APIRouter, status

from museums.dependencies import RegressionServiceDep
from museums.schemas.regression import RegressionResultOut

router = APIRouter(prefix="/regression", tags=["regression"])


@router.get(
    "",
    response_model=RegressionResultOut,
    status_code=status.HTTP_200_OK,
    summary="Fit the log-log regression on the harmonized dataset",
    description=(
        "Fits `log(visitors) ~ log(population_est)` via OLS and returns the "
        "coefficient (elasticity), intercept, R², sample size, timestamp, and "
        "per-point residuals. Raises 422 when fewer than 5 harmonized rows are "
        "available (the minimum for a meaningful fit)."
    ),
    responses={422: {"description": ("Fewer than 5 harmonized rows available — regression cannot be fit.")}},
)
async def get_regression(service: RegressionServiceDep) -> RegressionResultOut:
    """Fit a log-log regression model and return results. Returns 422 if <5 rows."""
    result = await service.fit()
    return RegressionResultOut.model_validate(result, from_attributes=True)
