"""Tests for RegressionService."""

from __future__ import annotations

import math

import pytest

from museums.exceptions import InsufficientDataError
from museums.services.harmonization_service import HarmonizedRow
from museums.services.regression_service import RegressionService


def _row(museum_name: str, city_name: str, pop: float, visitors: int, year: int = 2022) -> HarmonizedRow:
    return HarmonizedRow(
        museum_id=1,
        museum_name=museum_name,
        city_id=1,
        city_name=city_name,
        year=year,
        visitors=visitors,
        population_est=pop,
        population_is_extrapolated=False,
        population_fit_slope=None,
        population_fit_intercept=None,
    )


class _FakeHarmonization:
    def __init__(self, rows: list[HarmonizedRow]) -> None:
        self._rows = rows

    async def build_harmonized_rows(self) -> list[HarmonizedRow]:
        return self._rows


def _make_service(rows: list[HarmonizedRow]) -> RegressionService:
    return RegressionService(harmonization=_FakeHarmonization(rows))  # type: ignore[arg-type]


def _synthetic_rows(k: float = 1.0, alpha: float = 0.4, n: int = 10) -> list[HarmonizedRow]:
    """Generate rows where visitors = k * population^alpha (exact log-log linear)."""
    populations = [1_000_000 * (i + 1) for i in range(n)]
    return [_row(f"M{i}", f"C{i}", pop=float(p), visitors=max(1, int(k * p**alpha))) for i, p in enumerate(populations)]


@pytest.mark.asyncio
async def test_fit_returns_positive_coefficient_on_synthetic_log_linear_data() -> None:
    # Arrange — exact power-law: visitors = 1.0 * population^0.4
    rows = _synthetic_rows(alpha=0.4)
    service = _make_service(rows)

    # Act
    result = await service.fit()

    # Assert
    assert abs(result.coefficient - 0.4) < 0.05
    assert result.r_squared > 0.95


@pytest.mark.asyncio
async def test_fit_raises_insufficient_data_when_fewer_than_five_rows() -> None:
    # Arrange — only 4 rows
    rows = _synthetic_rows(n=4)
    service = _make_service(rows)

    # Act & Assert
    with pytest.raises(InsufficientDataError):
        await service.fit()


@pytest.mark.asyncio
async def test_fit_computes_r_squared_correctly_on_perfect_fit() -> None:
    # Arrange — exact log-log linear relationship (no noise)
    rows = _synthetic_rows(k=2.0, alpha=0.5, n=8)
    service = _make_service(rows)

    # Act
    result = await service.fit()

    # Assert — perfect fit yields R² very close to 1.0
    # Direct comparison: sklearn integer truncation introduces tiny floating-point noise
    assert abs(result.r_squared - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_fit_populates_points_with_predicted_and_residual() -> None:
    # Arrange
    rows = _synthetic_rows(n=5)
    service = _make_service(rows)

    # Act
    result = await service.fit()

    # Assert — residual must equal log_visitors - predicted_log_visitors
    for pt in result.points:
        expected_residual = pt.log_visitors - pt.predicted_log_visitors
        assert abs(pt.residual - expected_residual) < 1e-12


@pytest.mark.asyncio
async def test_fit_raises_insufficient_data_when_row_has_nonpositive_population() -> None:
    # Arrange — 5 rows but one has population_est=0 (log(0) is undefined)
    rows = _synthetic_rows(n=5)
    rows[2] = _row(rows[2].museum_name, rows[2].city_name, pop=0.0, visitors=rows[2].visitors)
    service = _make_service(rows)

    # Act & Assert
    with pytest.raises(InsufficientDataError):
        await service.fit()


@pytest.mark.asyncio
async def test_fit_uses_log_transform_on_both_axes() -> None:
    """Verify log-log transform: a power-law relationship must yield high R².

    The raw relationship (visitors = k * pop^0.3) is non-linear, but in
    log-log space it is exactly linear. A high R² confirms the transform.
    """
    # Arrange — power-law with exponent 0.3; raw scatter would give poor linear fit
    rows = _synthetic_rows(k=0.5, alpha=0.3, n=12)
    service = _make_service(rows)

    # Act
    result = await service.fit()

    # Assert — log-log transform recovers the linear structure
    assert result.r_squared > 0.99
    assert result.n_samples == 12
    for pt in result.points:
        assert math.isfinite(pt.log_population_est)
        assert math.isfinite(pt.log_visitors)
