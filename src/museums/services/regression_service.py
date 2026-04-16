"""Regression service — log-log linear regression on harmonized rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import numpy.typing as npt
from sklearn.linear_model import LinearRegression

from museums.exceptions import InsufficientDataError
from museums.services.harmonization_service import HarmonizationService, HarmonizedRow

_MIN_ROWS = 5

# sklearn stubs are incomplete; cast() narrows Unknown return types for pyright strict mode.
_FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class RegressionPoint:
    museum_name: str
    city_name: str
    year: int
    log_population_est: float
    log_visitors: float
    predicted_log_visitors: float
    residual: float


@dataclass(frozen=True)
class RegressionResult:
    coefficient: float
    intercept: float
    r_squared: float
    n_samples: int
    fitted_at: datetime
    points: list[RegressionPoint]


class RegressionService:
    """Fit log-log regression on harmonized museum/city rows.

    Note: depends on HarmonizationService (documented service-to-service
    exception — this is a pure compute pipeline, not a general pattern).
    """

    def __init__(self, harmonization: HarmonizationService) -> None:
        self._harmonization = harmonization

    async def fit(self) -> RegressionResult:
        """Build harmonized rows, fit log-log model, return RegressionResult."""
        rows = await self._harmonization.build_harmonized_rows()
        self._validate_rows(rows)
        x, y = self._build_arrays(rows)
        model, r2, y_pred = self._run_model(x, y)
        points = self._build_points(rows, y, y_pred)
        return RegressionResult(
            coefficient=model.coefficient,
            intercept=model.intercept,
            r_squared=r2,
            n_samples=len(rows),
            fitted_at=datetime.now(UTC),
            points=points,
        )

    def _validate_rows(self, rows: list[HarmonizedRow]) -> None:
        if len(rows) < _MIN_ROWS:
            raise InsufficientDataError(f"Regression requires >= {_MIN_ROWS} harmonized rows, got {len(rows)}")
        invalid = [r for r in rows if r.population_est <= 0 or r.visitors <= 0]
        if invalid:
            raise InsufficientDataError(
                f"Rows with non-positive population_est or visitors found: {len(invalid)} row(s)"
            )

    def _build_arrays(self, rows: list[HarmonizedRow]) -> tuple[_FloatArray, _FloatArray]:
        x: _FloatArray = np.log(np.array([r.population_est for r in rows], dtype=np.float64)).reshape(-1, 1)
        y: _FloatArray = np.log(np.array([r.visitors for r in rows], dtype=np.float64))
        return x, y

    def _run_model(self, x: _FloatArray, y: _FloatArray) -> tuple[_FitResult, float, _FloatArray]:
        """Fit sklearn model; annotate as Any to work around incomplete sklearn stubs."""
        # sklearn type stubs do not expose concrete return types — use Any for .fit()
        model: Any = LinearRegression()
        fitted: Any = model.fit(x, y)
        r2: float = float(fitted.score(x, y))
        y_pred: _FloatArray = fitted.predict(x)
        coef: float = float(fitted.coef_[0])
        intercept: float = float(fitted.intercept_)
        return _FitResult(coefficient=coef, intercept=intercept), r2, y_pred

    def _build_points(
        self,
        rows: list[HarmonizedRow],
        y: _FloatArray,
        y_pred: _FloatArray,
    ) -> list[RegressionPoint]:
        return [
            RegressionPoint(
                museum_name=row.museum_name,
                city_name=row.city_name,
                year=row.year,
                log_population_est=float(np.log(row.population_est)),
                log_visitors=float(y[i]),
                predicted_log_visitors=float(y_pred[i]),
                residual=float(y[i]) - float(y_pred[i]),
            )
            for i, row in enumerate(rows)
        ]


@dataclass(frozen=True)
class _FitResult:
    """Typed container for fitted sklearn coefficients."""

    coefficient: float
    intercept: float
