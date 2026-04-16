# Phase 4 — Harmonization & Regression Services

**Agent:** `python-fastapi`
**Depends on:** Phase 2 (models + repositories).
**Produces for Phase 5:** `HarmonizationService`, `RegressionService`.
**Parallelizable with Phase 3** — disjoint files.

This phase is pure compute: no HTTP, no external calls. Read models and
repositories; produce domain DTOs. Read `CLAUDE.md` §"Data & math" for the
algorithm contract.

## Algorithm recap

**Harmonization:**
1. For each city with ≥ 2 population records, fit a linear
   `population = a * year + b` via least-squares.
2. For each museum, pick the most recent visitor record (nearest-to-today;
   ties broken by max visitors).
3. Estimate city population at the museum's visitor year using the fit.
   If city has < 2 population records: use the single point only if within
   ±2y of the visitor year; else drop the museum (log warning).
4. Produce one `HarmonizedRow` per surviving museum.

**Regression:**
1. From ≥ 5 harmonized rows, build arrays `X = log(population_est)`,
   `y = log(visitors)`.
2. Fit `sklearn.linear_model.LinearRegression`.
3. Return `RegressionResult`: coefficient (elasticity), intercept, R²,
   list of `(museum_name, city_name, year, log_pop, log_visitors, predicted_log_visitors)`.

## Files to create (new)

### `src/museums/services/harmonization_service.py`
**Purpose:** Build the harmonized dataset from raw museum + population
records.
**Class:** `HarmonizationService`.
**Constructor:**
```python
def __init__(
    self,
    museum_repo: MuseumRepository,
    visitor_repo: VisitorRecordRepository,
    population_repo: PopulationRecordRepository,
) -> None: ...
```
**DTOs (in same file):**
```python
@dataclass(frozen=True)
class HarmonizedRow:
    museum_id: int
    museum_name: str
    city_id: int
    city_name: str
    year: int           # visitor-record year (source of truth for matching)
    visitors: int
    population_est: float  # estimated, not raw
    population_is_extrapolated: bool
    population_fit_slope: float | None    # None if single-point fallback
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
```

**Public method:**
```python
async def build_harmonized_rows(self) -> list[HarmonizedRow]: ...
```

**Algorithm (step by step, each step ≤ 30 lines):**
1. `museums = await museum_repo.list_paginated(skip=0, limit=10_000)` —
   include `visitor_records` and `city` via joinedload. Filter out
   museums without a `city` or without any `visitor_records`.
2. `populations_by_city = await population_repo.list_all_grouped()` —
   `{city_id: [records sorted by year]}`.
3. `fits = {city_id: self._fit_city(points) for city_id, points in populations_by_city.items() if len(points) >= 2}`.
4. For each museum:
   a. Pick visitor record: `sorted(visitor_records, key=lambda r: (-r.year, -r.visitors))[0]`.
   b. Look up `fit = fits.get(museum.city_id)`.
   c. If fit present → `pop_est = fit.slope * year + fit.intercept`;
      `is_extrapolated = (year < fit.min_year or year > fit.max_year)`.
   d. Else if city has exactly 1 population record and `abs(record.year - visitor_year) <= 2` → `pop_est = record.population`; `is_extrapolated = True`.
   e. Else log warning and skip museum.
   f. If `pop_est <= 0` (extrapolation gone wrong), log warning and skip.
   g. Append `HarmonizedRow`.
5. Return the list sorted by `-visitors`.

**Private helpers:**
- `def _fit_city(self, points: list[PopulationRecord]) -> CityFit` — use
  `numpy.polyfit(x=[r.year], y=[r.population], deg=1)` OR simple
  closed-form least-squares. Return `CityFit`.
- `def _pick_visitor_record(self, records: list[VisitorRecord]) -> VisitorRecord` —
  nearest-to-today with tie-break on max visitors.

**Constraints:**
- No HTTPException. Raise `InsufficientDataError("No museums have a city + visitor record")` if the final list is empty AND the raw inputs were non-empty.
- Use `structlog.get_logger("harmonization")` for drop reasons.
- Never mutate ORM model instances.

### `src/museums/services/regression_service.py`
**Purpose:** Fit the log-log regression on harmonized rows.
**Class:** `RegressionService`.
**Constructor:**
```python
def __init__(self, harmonization: HarmonizationService) -> None: ...
```
**Note — service-to-service dependency (documented exception):**
`RegressionService` depends on `HarmonizationService` (not on repos
directly). This is a deliberate composition for a compute pipeline —
regression doesn't want to re-derive harmonization from scratch. Phase 6
adds an ADR to `decisions.md` documenting the exception.

**DTOs (in same file):**
```python
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
    coefficient: float         # slope in log-log space = elasticity
    intercept: float
    r_squared: float
    n_samples: int
    fitted_at: datetime
    points: list[RegressionPoint]
```

**Public method:**
```python
async def fit(self) -> RegressionResult: ...
```

**Algorithm:**
1. `rows = await self._harmonization.build_harmonized_rows()`.
2. If `len(rows) < 5`: raise `InsufficientDataError(f"Regression requires ≥ 5 harmonized rows, got {len(rows)}")`.
3. Build `numpy` arrays: `x = np.log(np.array([r.population_est for r in rows], dtype=float)).reshape(-1, 1)`; `y = np.log(np.array([r.visitors for r in rows], dtype=float))`.
4. Guard: if any row has `population_est <= 0` or `visitors <= 0`, raise `InsufficientDataError` (should have been filtered earlier; defensive).
5. `model = LinearRegression().fit(x, y)`; `r2 = model.score(x, y)`; `y_pred = model.predict(x)`.
6. Build `points` list from rows + predicted values.
7. Return `RegressionResult(coefficient=float(model.coef_[0]), intercept=float(model.intercept_), r_squared=float(r2), n_samples=len(rows), fitted_at=datetime.now(timezone.utc), points=points)`.

**Constraints:**
- No persistence in Phase 4 — this service fits and returns; we do NOT
  store regression results in the DB. Rationale: it's cheap to re-run and
  the data is small.
- Imports: `from sklearn.linear_model import LinearRegression`;
  `import numpy as np`.

## Test files

### `tests/test_services/test_harmonization_service.py`
**Tests (8):**
- `test_build_harmonized_rows_fits_per_city_and_matches_museum_year` —
  seed city with populations 2015=2_000_000, 2020=2_100_000; museum with
  visitor record year=2023; assert `population_est ≈ 2_140_000`
  (extrapolated via slope).
- `test_build_harmonized_rows_uses_single_point_fallback_within_2y` —
  seed city with 1 population record at year=2021; museum visitor
  record year=2023; assert `pop_est == record.population`, `is_extrapolated=True`.
- `test_build_harmonized_rows_skips_single_point_when_far` — same but
  visitor year=2010; assert museum skipped.
- `test_build_harmonized_rows_picks_most_recent_visitor_record` — museum
  with 3 visitor records (2019, 2022, 2023); assert row year=2023.
- `test_build_harmonized_rows_skips_museum_without_city` — museum with
  `city_id=None`; assert not in output.
- `test_build_harmonized_rows_skips_city_with_zero_population_records` —
  museum has city but city has no population data; assert skipped.
- `test_build_harmonized_rows_sorts_by_visitors_descending` — seed 3
  museums; assert result order.
- `test_build_harmonized_rows_flags_extrapolation_outside_fit_range` —
  fit on 2015–2020; visitor year 2024; assert `is_extrapolated=True`.

### `tests/test_services/test_regression_service.py`
**Tests (5):**
- `test_fit_returns_positive_coefficient_on_synthetic_log_linear_data` —
  seed rows where `visitors = k * population^0.4`; fit; assert
  `coefficient ≈ 0.4` (within 0.05) and `r_squared > 0.95`.
- `test_fit_raises_insufficient_data_when_fewer_than_five_rows` — stub
  `build_harmonized_rows` to return 4 rows; assert `InsufficientDataError`.
- `test_fit_computes_r_squared_correctly_on_perfect_fit` — exact
  log-linear relationship; assert `r_squared == pytest.approx(1.0, abs=1e-9)`.
- `test_fit_populates_points_with_predicted_and_residual` — 5 rows;
  assert each `RegressionPoint.residual == point.log_visitors - point.predicted_log_visitors`.
- `test_fit_uses_log_transform_on_both_axes` — seed rows where raw
  relationship is non-linear but log-log IS linear; assert high R².
**Stubs:** Use a fake `HarmonizationService` (simple class returning a
pre-built list) — don't exercise the harmonization path in these tests.

## Phase 4 tooling gate

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest -v
uv run lint-imports
```

Expected new tests: 13 (8 + 5). Cumulative: 43.

## Out of scope for Phase 4

- No routers (Phase 5).
- No persistence of regression results.
- No client code.
- No cross-city regression stratification.
- `src/museums/dependencies.py` not touched — Phase 5 wires services.
