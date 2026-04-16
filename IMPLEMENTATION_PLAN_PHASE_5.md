# Phase 5 — API Layer

**Agent:** `python-fastapi`
**Depends on:** Phase 3 (clients + ingestion) AND Phase 4 (harmonization +
regression).
**Produces for Phase 6:** Full HTTP surface for the notebook to call.

Read `CLAUDE.md` before starting. Layer rules matter most in this phase —
routers are the thinnest layer.

## Endpoint contract

| Method | Path | Returns | Status | Notes |
|---|---|---|---|---|
| GET | `/health` | `{"status":"ok"}` | 200 | DB ping. Fails → 503. |
| POST | `/refresh` | `RefreshResultOut` | 202 | `?force=true` optional. |
| GET | `/museums` | `PaginatedMuseumsOut` | 200 | `skip`, `limit`. |
| GET | `/cities/populations` | `list[CityPopulationsOut]` | 200 | Full series per city (small N). |
| GET | `/harmonized` | `list[HarmonizedRowOut]` | 200 | Computed on demand. |
| GET | `/regression` | `RegressionResultOut` | 200 | Computed on demand. Returns 422 if <5 rows. |

## Files to create (new)

### `src/museums/schemas/__init__.py`
Re-export all response schemas.

### `src/museums/schemas/common.py`
**Purpose:** Shared DTOs (pagination, error envelope, health).
**Classes:**
```python
class ErrorOut(BaseModel):
    detail: str
    code: str        # e.g. "refresh_cooldown", "external_unavailable"

class PaginationMeta(BaseModel):
    total: int
    skip: int
    limit: int

class HealthOut(BaseModel):
    status: Literal["ok"]
```

### `src/museums/schemas/museum.py`
**Classes:**
```python
class VisitorRecordOut(BaseModel):
    year: int
    visitors: int
    model_config = ConfigDict(from_attributes=True)

class MuseumOut(BaseModel):
    id: int
    name: str
    wikipedia_title: str
    wikidata_qid: str | None
    city_name: str | None
    country: str | None
    visitor_records: list[VisitorRecordOut]
    model_config = ConfigDict(from_attributes=True)

class PaginatedMuseumsOut(BaseModel):
    items: list[MuseumOut]
    pagination: PaginationMeta
```
**Constraint:** `MuseumOut.city_name` is flattened from the relationship —
use a `@field_validator` or build in the service.

### `src/museums/schemas/city.py`
**Classes:**
```python
class PopulationPointOut(BaseModel):
    year: int
    population: int
    model_config = ConfigDict(from_attributes=True)

class CityPopulationsOut(BaseModel):
    id: int
    name: str
    wikidata_qid: str
    country: str | None
    population_history: list[PopulationPointOut]
    model_config = ConfigDict(from_attributes=True)
```

### `src/museums/schemas/harmonized.py`
**Classes:**
```python
class HarmonizedRowOut(BaseModel):
    museum_id: int
    museum_name: str
    city_id: int
    city_name: str
    year: int
    visitors: int
    population_est: float
    population_is_extrapolated: bool
```

### `src/museums/schemas/regression.py`
**Classes:**
```python
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
```

### `src/museums/schemas/refresh.py`
**Classes:**
```python
class RefreshResultOut(BaseModel):
    museums_refreshed: int
    cities_refreshed: int
    visitor_records_upserted: int
    population_records_upserted: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float

    @classmethod
    def from_summary(cls, summary: RefreshSummary) -> RefreshResultOut: ...
```

### `src/museums/services/museum_query_service.py`
**Purpose:** Thin read-only service so routers don't import repositories
directly (CLAUDE.md router-layer rule + import-linter contract 1). No
business logic — just pagination plumbing + schema mapping.
**Class:** `MuseumQueryService`.
**Constructor:** `__init__(self, museum_repo: MuseumRepository) -> None`.
**Public method:**
```python
async def list_paginated(self, skip: int, limit: int) -> PaginatedMuseumsOut: ...
```
**Implementation:** call `museum_repo.list_paginated(skip, limit)` →
`(items, total)` → build `PaginatedMuseumsOut(items=[MuseumOut.model_validate(m, from_attributes=True) ...], pagination=PaginationMeta(total=total, skip=skip, limit=limit))`.
**Constraint:** No raw dicts — returns `PaginatedMuseumsOut` directly.
≤ 40 lines including imports.

### `src/museums/services/city_query_service.py`
**Purpose:** Thin read-only service for cities + their population history.
**Class:** `CityQueryService`.
**Constructor:** `__init__(self, city_repo: CityRepository, population_repo: PopulationRecordRepository) -> None`.
**Public method:**
```python
async def list_with_populations(self) -> list[CityPopulationsOut]: ...
```
**Implementation:** fetch `cities = await city_repo.list_all()` and
`grouped = await population_repo.list_all_grouped()`; build the DTO list
as in the previous cities-router spec.
**Constraint:** ≤ 40 lines. No business logic.

### `src/museums/dependencies.py`
**Purpose:** All FastAPI `Depends()` chains for the project.
**Contents:**
- `SettingsDep = Annotated[Settings, Depends(get_settings)]`.
- `async def get_engine(settings: SettingsDep) -> AsyncEngine` — cached via `lru_cache` on the factory, OR stored on `app.state` at lifespan.
- `async def get_session(engine: ...) -> AsyncIterator[AsyncSession]` — yields a session bound to an async transaction.
- `async def get_http_client(request: Request) -> httpx.AsyncClient` — reads from `request.app.state.http_client` (populated in lifespan).
- Repository factories: `async def get_city_repo(session: ...) -> CityRepository`, etc.
- Client factories: `async def get_mediawiki_client(client: ..., settings: ...) -> MediaWikiClient`, etc.
- **Ingestion deps factory:** `async def get_ingestion_deps(...) -> IngestionDeps` — composes the 5 repos into the dataclass from Phase 3.
- Workflow factory: `async def get_ingestion_workflow(mediawiki, wikidata, session, settings, deps: IngestionDeps) -> IngestionWorkflow`.
- Service factories:
  - `async def get_museum_query_service(museum_repo: ...) -> MuseumQueryService`
  - `async def get_city_query_service(city_repo: ..., population_repo: ...) -> CityQueryService`
  - `async def get_harmonization_service(...) -> HarmonizationService`
  - `async def get_regression_service(harmonization: ...) -> RegressionService`
- `Annotated` aliases: `IngestionWorkflowDep`, `MuseumQueryServiceDep`, `CityQueryServiceDep`, `HarmonizationServiceDep`, `RegressionServiceDep`, `SessionDep`.
**Constraint:** No business logic. This file is wiring only. Keep under
150 lines.

### `src/museums/routers/__init__.py`
**Purpose:** Re-export routers; central `api_router` combining them.
**Contents:**
```python
from fastapi import APIRouter
from .cities import router as cities_router
from .harmonized import router as harmonized_router
from .health import router as health_router
from .museums import router as museums_router
from .refresh import router as refresh_router
from .regression import router as regression_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(refresh_router)
api_router.include_router(museums_router)
api_router.include_router(cities_router)
api_router.include_router(harmonized_router)
api_router.include_router(regression_router)
```

### `src/museums/routers/health.py`
**Router:** `APIRouter(prefix="/health", tags=["health"])`.
**Endpoint:**
```python
@router.get("", response_model=HealthOut, status_code=status.HTTP_200_OK)
async def health(session: SessionDep) -> HealthOut:
    await session.execute(text("SELECT 1"))
    return HealthOut(status="ok")
```
**Constraint:** On DB failure the exception handler returns 503. Import
`HealthOut` from `src.museums.schemas.common`.

### `src/museums/routers/refresh.py`
**Router:** `APIRouter(prefix="/refresh", tags=["refresh"])`.
**Endpoint:**
```python
from fastapi import APIRouter, Query, status

router = APIRouter(prefix="/refresh", tags=["refresh"])

@router.post("", response_model=RefreshResultOut, status_code=status.HTTP_202_ACCEPTED)
async def refresh(
    workflow: IngestionWorkflowDep,
    force: bool = Query(default=False, description="Bypass the cooldown check."),
) -> RefreshResultOut:
    summary = await workflow.refresh(force=force)
    return RefreshResultOut.from_summary(summary)
```
**Constraint:** Non-defaulted `Annotated[..., Depends(...)]` params come
before defaulted `Query(...)` params — required by FastAPI/Python.

### `src/museums/routers/museums.py`
**Router:** `APIRouter(prefix="/museums", tags=["museums"])`.
**Endpoint:**
```python
@router.get("", response_model=PaginatedMuseumsOut, status_code=status.HTTP_200_OK)
async def list_museums(
    service: MuseumQueryServiceDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> PaginatedMuseumsOut:
    return await service.list_paginated(skip=skip, limit=limit)
```
**Constraint:** Router does NOT import repositories or models — routes
through `MuseumQueryService` per CLAUDE.md + import-linter contract 1.

### `src/museums/routers/cities.py`
**Router:** `APIRouter(prefix="/cities", tags=["cities"])`.
**Endpoint:**
```python
@router.get("/populations", response_model=list[CityPopulationsOut], status_code=status.HTTP_200_OK)
async def list_city_populations(service: CityQueryServiceDep) -> list[CityPopulationsOut]:
    return await service.list_with_populations()
```
**Constraint:** Router goes through `CityQueryService`, not the repos.

### `src/museums/routers/harmonized.py`
**Router:** `APIRouter(prefix="/harmonized", tags=["harmonized"])`.
**Endpoint:**
```python
@router.get("", response_model=list[HarmonizedRowOut], status_code=200)
async def get_harmonized(service: HarmonizationServiceDep) -> list[HarmonizedRowOut]:
    rows = await service.build_harmonized_rows()
    return [HarmonizedRowOut.model_validate(r, from_attributes=True) for r in rows]
```

### `src/museums/routers/regression.py`
**Router:** `APIRouter(prefix="/regression", tags=["regression"])`.
**Endpoint:**
```python
@router.get("", response_model=RegressionResultOut, status_code=200)
async def get_regression(service: RegressionServiceDep) -> RegressionResultOut:
    result = await service.fit()
    return RegressionResultOut.model_validate(result, from_attributes=True)
```

## Files to modify

### `src/museums/main.py` (COMPLETE)
**Changes:**
1. In `lifespan`: also build the shared `httpx.AsyncClient` and store on
   `app.state.http_client`; close it on shutdown.
2. Register `api_router` via `app.include_router(api_router)`.
3. Register exception handlers:
   - `NotFoundError` → 404, body `ErrorOut(detail=str(exc), code="not_found")`.
   - `RefreshCooldownError` → 429, body + `Retry-After` header set to `exc.retry_after_seconds`.
   - `MediaWikiUnavailableError` / `WikidataUnavailableError` → 503, body with `code="external_unavailable"`.
   - `ExternalDataParseError` → 502, body with `code="external_parse_error"`.
   - `InsufficientDataError` → 422, body with `code="insufficient_data"`.
4. **No CORS middleware.** The notebook calls the API from inside the
   jupyter kernel (server-side Python `requests`), not from a browser, so
   CORS is irrelevant. Adding it would be dead weight.
**Constraint:** Keep `main.py` ≤ 150 lines. Extract handlers into
`src/museums/exception_handlers.py` if it grows past that.

## Test files

### `tests/conftest.py` (MODIFY — extend Phase 2 version)
**Add:**
- `async def app_client(async_engine) -> AsyncIterator[httpx.AsyncClient]` — builds
  the app, overrides `get_session` to use the test engine, yields an
  `httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`.
- Dep overrides for `IngestionServiceDep` when tests need to stub the
  clients (use `app.dependency_overrides`).

### `tests/test_routers/__init__.py`
Empty.

### `tests/test_services/test_museum_query_service.py`
**Tests (2):**
- `test_list_paginated_returns_paginated_museums_out` — seed 3 museums;
  assert the DTO has 3 items and `pagination.total == 3`.
- `test_list_paginated_empty_returns_zero_total` — no museums seeded;
  assert `items == []` and `pagination.total == 0`.

### `tests/test_services/test_city_query_service.py`
**Tests (2):**
- `test_list_with_populations_groups_by_city` — 2 cities × 2 population
  records each; assert 2 `CityPopulationsOut` entries each with 2 points.
- `test_list_with_populations_returns_empty_history_for_city_without_records` —
  1 city with no populations; assert `population_history == []`.

### `tests/test_routers/test_health.py`
**Tests (1):**
- `test_health_returns_ok_when_db_reachable` — assert 200 + `{"status":"ok"}`.

### `tests/test_routers/test_refresh.py`
**Tests (4):**
- `test_refresh_returns_202_with_summary_on_success` — override
  `IngestionWorkflow` stub that returns a fixture `RefreshSummary`;
  assert response body shape.
- `test_refresh_returns_429_with_retry_after_on_cooldown` — stub raises
  `RefreshCooldownError(3600)`; assert status 429, header `Retry-After: 3600`,
  body `code == "refresh_cooldown"`.
- `test_refresh_returns_503_when_mediawiki_unavailable` — stub raises
  `MediaWikiUnavailableError()`; assert status 503, body `code == "external_unavailable"` and `service_name == "mediawiki"` present in the payload.
  Parametrize the same test on `WikidataUnavailableError` → 503 +
  `service_name == "wikidata"`.
- `test_refresh_with_force_param_calls_workflow_with_force_true` — assert
  the stub was called with `force=True` when `?force=true`.

### `tests/test_routers/test_museums.py`
**Tests (2):**
- `test_list_museums_returns_paginated_response` — seed 3 museums; assert
  `items` count, `pagination.total=3`.
- `test_list_museums_limit_caps_at_200` — pass `limit=500`; assert 422.

### `tests/test_routers/test_cities.py`
**Tests (1):**
- `test_list_city_populations_returns_series_per_city` — seed 2 cities
  with 3 population records each; assert response shape.

### `tests/test_routers/test_harmonized.py`
**Tests (1):**
- `test_get_harmonized_returns_rows_when_data_present` — seed minimal
  data (1 museum, 1 city, 2 population records, 1 visitor record); assert
  1 row returned.

### `tests/test_routers/test_regression.py`
**Tests (2):**
- `test_get_regression_returns_fit_when_enough_data` — seed 6 museums with
  log-linear relationship; assert 200, `coefficient` in range.
- `test_get_regression_returns_422_when_insufficient_data` — seed only 2
  museums; assert 422 with `code="insufficient_data"`.

## Phase 5 tooling gate

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest -v
uv run lint-imports
curl -fsS http://localhost:8000/health   # after docker compose up --build
```

Expected new tests: 15 (1 health + 4 refresh + 2 museums + 1 cities + 1 harmonized + 2 regression + 2 museum-query-service + 2 city-query-service). Cumulative: 58.

## Out of scope for Phase 5

- No notebook (Phase 6).
- No final `ARCHITECTURE.md` / `decisions.md` (Phase 6).
- No auth, rate limiting.
