"""Harmonization service — per-city OLS fit and nearest-year population estimate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt
import structlog

# Repository and model imports are TYPE_CHECKING-only: keeps this module out of
# SQLAlchemy's import graph (services cannot import sqlalchemy per layer contract).
if TYPE_CHECKING:
    from museums.models.population_record import PopulationRecord
    from museums.models.visitor_record import VisitorRecord
    from museums.repositories.museum_repository import MuseumRepository
    from museums.repositories.population_record_repository import PopulationRecordRepository
    from museums.repositories.visitor_record_repository import VisitorRecordRepository

_log = structlog.get_logger("harmonization")


@dataclass(frozen=True)
class HarmonizedRow:
    museum_id: int
    museum_name: str
    city_id: int
    city_name: str
    year: int
    visitors: int
    population_est: float
    population_is_extrapolated: bool
    population_fit_slope: float | None
    population_fit_intercept: float | None


@dataclass(frozen=True)
class CityFit:
    """Internal helper — per-city OLS parameters."""

    city_id: int
    slope: float
    intercept: float
    n_points: int
    min_year: int
    max_year: int


class HarmonizationService:
    """Build the harmonized dataset from raw museum and population records."""

    def __init__(
        self,
        museum_repo: MuseumRepository,
        visitor_repo: VisitorRecordRepository,
        population_repo: PopulationRecordRepository,
    ) -> None:
        self._museum_repo = museum_repo
        self._visitor_repo = visitor_repo
        self._population_repo = population_repo

    async def build_harmonized_rows(self) -> list[HarmonizedRow]:
        """Return one HarmonizedRow per surviving museum, sorted by -visitors."""
        museums_raw, _ = await self._museum_repo.list_paginated(skip=0, limit=10_000)
        eligible = [m for m in museums_raw if m.city is not None and m.visitor_records]
        if not eligible:
            return []

        populations_by_city = await self._population_repo.list_all_grouped()
        fits = self._build_fits(populations_by_city)
        rows = self._build_rows(eligible, populations_by_city, fits)
        return sorted(rows, key=lambda r: -r.visitors)

    def _build_fits(
        self,
        populations_by_city: dict[int, list[PopulationRecord]],
    ) -> dict[int, CityFit]:
        return {
            city_id: self._fit_city(city_id, points)
            for city_id, points in populations_by_city.items()
            if len(points) >= 2
        }

    def _fit_city(self, city_id: int, points: list[PopulationRecord]) -> CityFit:
        """Compute OLS slope/intercept from >= 2 population records."""
        years: npt.NDArray[np.float64] = np.array([r.year for r in points], dtype=float)
        pops: npt.NDArray[np.float64] = np.array([r.population for r in points], dtype=float)
        coeffs: npt.NDArray[Any] = np.polyfit(years, pops, deg=1)
        return CityFit(
            city_id=city_id,
            slope=float(coeffs[0]),
            intercept=float(coeffs[1]),
            n_points=len(points),
            min_year=int(min(r.year for r in points)),
            max_year=int(max(r.year for r in points)),
        )

    def _pick_visitor_record(self, records: list[VisitorRecord]) -> VisitorRecord:
        """Return most recent record, tie-breaking on max visitors."""
        return sorted(records, key=lambda r: (-r.year, -r.visitors))[0]

    def _build_rows(
        self,
        eligible: list[Any],
        populations_by_city: dict[int, list[PopulationRecord]],
        fits: dict[int, CityFit],
    ) -> list[HarmonizedRow]:
        rows: list[HarmonizedRow] = []
        for museum in eligible:
            row = self._process_museum(museum, populations_by_city, fits)
            if row is not None:
                rows.append(row)
        return rows

    def _process_museum(
        self,
        museum: Any,
        populations_by_city: dict[int, list[PopulationRecord]],
        fits: dict[int, CityFit],
    ) -> HarmonizedRow | None:
        city = museum.city
        record = self._pick_visitor_record(museum.visitor_records)
        visitor_year = record.year
        pop_est, is_extrapolated, slope, intercept = self._estimate_population(
            museum.id, city.id, visitor_year, populations_by_city, fits
        )
        if pop_est is None:
            return None
        if pop_est <= 0:
            _log.warning("population_est_nonpositive", museum_id=museum.id, city_id=city.id, pop_est=pop_est)
            return None
        return HarmonizedRow(
            museum_id=museum.id,
            museum_name=museum.name,
            city_id=city.id,
            city_name=city.name,
            year=visitor_year,
            visitors=record.visitors,
            population_est=pop_est,
            population_is_extrapolated=is_extrapolated,
            population_fit_slope=slope,
            population_fit_intercept=intercept,
        )

    def _estimate_population(
        self,
        museum_id: int,
        city_id: int,
        visitor_year: int,
        populations_by_city: dict[int, list[PopulationRecord]],
        fits: dict[int, CityFit],
    ) -> tuple[float | None, bool, float | None, float | None]:
        """Return (pop_est, is_extrapolated, slope, intercept) or (None, ...) to skip."""
        fit = fits.get(city_id)
        if fit is not None:
            pop_est = fit.slope * visitor_year + fit.intercept
            is_ext = visitor_year < fit.min_year or visitor_year > fit.max_year
            return pop_est, is_ext, fit.slope, fit.intercept

        city_records = populations_by_city.get(city_id, [])
        if len(city_records) == 1 and abs(city_records[0].year - visitor_year) <= 2:
            return float(city_records[0].population), True, None, None

        _log.warning(
            "museum_skipped_no_population_fit",
            museum_id=museum_id,
            city_id=city_id,
            visitor_year=visitor_year,
            reason="no fit and no usable single-point fallback",
        )
        return None, False, None, None
