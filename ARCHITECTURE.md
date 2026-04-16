# Architecture

Design rationale: [`docs/PROJECT.md`](docs/PROJECT.md)

## Overview

A FastAPI service that fetches the most-visited museums from Wikipedia (MediaWiki
Action API) and enriches them with structured visitor counts and city population
time series from Wikidata SPARQL. A per-city OLS fit bridges the year gap between
museum visitor records and population records, producing a harmonized dataset.
A log-log linear regression quantifies the elasticity of museum attendance with
respect to city population. All results are exposed as JSON endpoints consumed
by a companion Jupyter notebook that renders the analysis visually.

## Tech Stack

- **Python 3.13** — language; `uv` for dependency management.
- **FastAPI** — async HTTP framework; Pydantic v2 for request/response DTOs.
- **SQLAlchemy 2.0 async** + **asyncpg** + **Alembic** — ORM, driver, migrations.
- **PostgreSQL 16** — database, run via Docker Compose.
- **httpx** — async HTTP client for all external API calls.
- **tenacity** — exponential-backoff retry on 429/5xx responses.
- **mwparserfromhell** — wikitext parser for the MediaWiki Action API response.
- **scikit-learn** — `LinearRegression` for the log-log regression.
- **numpy / pandas** — array math and DataFrame helpers (used in services).
- **structlog** — structured JSON logging with bound context.
- **Jupyter** (`jupyter/minimal-notebook` base image) — notebook container.

## Project Structure

```
src/museums/
├── main.py                  # App factory, lifespan (DB ping, HTTP client setup)
├── config.py                # Settings via pydantic-settings (DB URL, cooldown, timeouts)
├── dependencies.py          # Annotated Depends() aliases wiring all layers
├── exceptions.py            # Domain exception hierarchy (DomainError subclasses)
├── exception_handlers.py    # FastAPI handlers mapping domain errors to HTTP status codes
├── http_client.py           # Shared httpx.AsyncClient factory + lifespan context manager
├── logging_config.py        # structlog setup called from lifespan
├── routers/
│   ├── health.py            # GET /health
│   ├── refresh.py           # POST /refresh — delegates to IngestionWorkflow
│   ├── museums.py           # GET /museums — paginated list
│   ├── cities.py            # GET /cities/populations — full population time series
│   ├── harmonized.py        # GET /harmonized — museum/population pairs
│   └── regression.py        # GET /regression — log-log fit result
├── workflows/
│   └── ingestion_workflow.py  # Orchestrates clients + 5 repos under one transaction
├── services/
│   ├── museum_query_service.py     # Paginated museum list with visitor records
│   ├── city_query_service.py       # City population time series
│   ├── harmonization_service.py    # Per-city OLS fit + nearest-year population estimate
│   └── regression_service.py      # Log-log LinearRegression on harmonized rows
├── repositories/
│   ├── museum_repository.py        # Museum CRUD + upsert_by_name + list_paginated
│   ├── city_repository.py          # City upsert_by_qid + get_by_qid
│   ├── visitor_record_repository.py   # VisitorRecord upsert_many
│   ├── population_record_repository.py  # PopulationRecord upsert_many + list_all_grouped
│   └── refresh_state_repository.py    # RefreshState get + mark_refreshed
├── clients/
│   ├── mediawiki_client.py  # MediaWiki Action API — museum list via wikitext parse
│   └── wikidata_client.py   # Wikidata SPARQL — museum enrichment + city populations
├── models/
│   ├── base.py              # DeclarativeBase + TimestampMixin
│   ├── museum.py            # Museum ORM model
│   ├── city.py              # City ORM model
│   ├── visitor_record.py    # VisitorRecord ORM model (year, visitors per museum)
│   ├── population_record.py # PopulationRecord ORM model (year, population per city)
│   └── refresh_state.py     # RefreshState singleton (last_refresh_at)
├── schemas/
│   ├── museum.py            # MuseumOut, MuseumListOut
│   ├── city.py              # CityWithPopulationsOut
│   ├── harmonized.py        # HarmonizedRowOut
│   ├── regression.py        # RegressionResultOut, RegressionPointOut
│   ├── refresh.py           # RefreshResultOut
│   └── common.py            # PaginationOut
```

## Layer Responsibilities

### Routers — HTTP only

Parse request parameters, call one service or workflow, return a typed
`response_model`. No business logic, no repository imports, no ORM models.

```python
# routers/refresh.py
@router.post("", response_model=RefreshResultOut, status_code=status.HTTP_202_ACCEPTED)
async def refresh(
    workflow: IngestionWorkflowDep,
    force: bool = Query(default=False, description="Bypass the cooldown check."),
) -> RefreshResultOut:
    summary = await workflow.refresh(force=force)
    return RefreshResultOut.from_summary(summary)
```

### Services — business logic

Receive injected repositories, apply domain logic, return Pydantic schemas or
frozen dataclasses. Never import `AsyncSession`, never call `commit()`.

```python
# services/harmonization_service.py
class HarmonizationService:
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
        museums_raw, _ = await self._museum_repo.list_paginated(skip=0, limit=10_000)
        eligible = [m for m in museums_raw if m.city is not None and m.visitor_records]
        if not eligible:
            return []
        populations_by_city = await self._population_repo.list_all_grouped()
        fits = self._build_fits(populations_by_city)
        rows = self._build_rows(eligible, populations_by_city, fits)
        return sorted(rows, key=lambda r: -r.visitors)
```

### Workflows — transaction boundary

The only layer that holds `AsyncSession` and calls `commit()` / `rollback()`.
Coordinates multiple repositories and clients for operations that must be
all-or-nothing.

```python
# workflows/ingestion_workflow.py
async def refresh(self, *, force: bool) -> RefreshSummary:
    started_at = datetime.now(UTC)
    await self._check_cooldown(force)
    try:
        summary = await self._run(started_at, log)
    except Exception:
        await self._session.rollback()
        raise
    await self._session.commit()
    return summary
```

### Repositories — data access only

The only layer that imports ORM models and `AsyncSession`. Returns ORM instances;
services convert them to schemas. No business logic.

```python
# repositories/museum_repository.py
async def list_paginated(self, skip: int, limit: int) -> tuple[list[Museum], int]:
    total_result = await self._session.execute(select(func.count()).select_from(Museum))
    total = total_result.scalar_one()
    items_result = await self._session.execute(
        select(Museum)
        .options(joinedload(Museum.city), selectinload(Museum.visitor_records))
        .offset(skip).limit(limit).order_by(Museum.name)
    )
    return list(items_result.unique().scalars().all()), total
```

### Clients — external API surface

Wrap all external HTTP calls behind domain methods. Raise domain exceptions
(`MediaWikiUnavailableError`, `WikidataUnavailableError`, `ExternalDataParseError`)
— never let raw `httpx.*` errors escape. Use the shared `httpx.AsyncClient`
with tenacity retry built in.

### Models — database structure only

SQLAlchemy 2.0 `Mapped[]` / `mapped_column()` style. No methods with business
logic.

### Schemas — Pydantic DTOs

Separate schemas per purpose (`Out` for responses). `ConfigDict(from_attributes=True)`
for ORM integration. Never expose ORM models directly through the API.

### Exceptions — domain hierarchy

`DomainError` base with typed subclasses. `exception_handlers.py` maps each
subclass to an HTTP status code. Services raise domain exceptions; routers
never raise `HTTPException` directly.

## Data Flow

### `POST /refresh?force=false`

1. `routers/refresh.py` parses `force` query param, injects `IngestionWorkflow`.
2. `IngestionWorkflow.refresh()` checks `refresh_state.last_refresh_at` via
   `RefreshStateRepository`; raises `RefreshCooldownError` if within 24 h.
3. `MediaWikiClient.fetch_museum_list()` calls the MediaWiki Action API, parses
   wikitext with `mwparserfromhell`, returns a list of Wikipedia titles.
4. `WikidataClient.fetch_museum_enrichment()` runs a SPARQL query to enrich each
   museum with QID, city, country, and per-year visitor records (P1174 + P585).
5. `WikidataClient.fetch_city_populations()` runs a second SPARQL query for
   historical city populations (P1082 + P585), filtered to year ≥ 2000.
6. Workflow upserts cities via `CityRepository.upsert_by_qid`, museums via
   `MuseumRepository.upsert_by_name`, visitor records via
   `VisitorRecordRepository.upsert_many`, population records via
   `PopulationRecordRepository.upsert_many`, then calls
   `RefreshStateRepository.mark_refreshed`.
7. `session.commit()` on success; `session.rollback()` on any exception.
8. Router returns `RefreshResultOut` with HTTP 202.

### `GET /regression`

1. `routers/regression.py` injects `RegressionService`.
2. `RegressionService.fit()` calls `HarmonizationService.build_harmonized_rows()`.
3. `HarmonizationService` loads all museums (with city + visitor records) via
   `MuseumRepository.list_paginated` and all population records grouped by city
   via `PopulationRecordRepository.list_all_grouped`.
4. For each city with ≥ 2 population points, a per-city OLS slope/intercept is
   computed with `numpy.polyfit`. Single-point cities use a ±2y tolerance fallback.
5. For each museum, the most recent visitor record is selected; the city's
   population at that year is estimated from the OLS fit.
6. `RegressionService` takes the resulting `list[HarmonizedRow]`, builds log arrays,
   fits `sklearn.LinearRegression`, and wraps the result in `RegressionResult`.
7. Router validates to `RegressionResultOut` schema and returns HTTP 200.

## Key Domain Concepts

| Concept | Description |
|---|---|
| `Museum` | A high-traffic museum (> 2 M visitors/year) identified by Wikipedia title and Wikidata QID. Linked to a City. |
| `City` | Administrative city entity from Wikidata (QID + label). One city can host multiple museums. |
| `VisitorRecord` | One (museum, year, visitors) data point from Wikidata P1174 + P585. A museum has many. |
| `PopulationRecord` | One (city, year, population) data point from Wikidata P1082 + P585. A city has many. |
| `RefreshState` | Singleton table row tracking the last successful ingestion timestamp. |
| `HarmonizedRow` | Derived: one row per museum after OLS interpolation — (museum, city, year, visitors, population_est). Not persisted. |
| `RegressionResult` | Derived: log-log OLS fit output — coefficient, intercept, R², per-point scatter data. Not persisted. |

## State Machines

None — no stateful entities in this domain. `RefreshState` records a timestamp
but has no lifecycle transitions.
