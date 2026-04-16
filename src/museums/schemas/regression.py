"""Regression result response DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegressionPointOut(BaseModel):
    museum_name: str
    city_name: str
    year: int
    log_population_est: float
    log_visitors: float
    predicted_log_visitors: float
    residual: float


class RegressionResultOut(BaseModel):
    coefficient: float
    intercept: float
    r_squared: float
    n_samples: int
    fitted_at: datetime
    points: list[RegressionPointOut]
