# Architecture Decision Records

## 2026-04-16 — Add allow_indirect_imports to routers import-linter contract

**Status:** accepted

**Context:**
Phase 5 introduced `dependencies.py` as the central DI wiring layer. This file necessarily imports repositories, models, and clients (it is their factory). The `museums.routers` import-linter contract was configured without `allow_indirect_imports`, causing all transitive paths through `dependencies.py` to fail the "Routers cannot import repositories, models, or clients" contract.

**Decision:**
Add `allow_indirect_imports = "True"` to the routers contract. Direct imports from any router file into repositories/models/clients remain forbidden — the contract still catches the architectural violation it was designed for. Transitive paths through `dependencies.py` are permitted because `dependencies.py` is explicitly the wiring layer whose job is to import and compose these modules.

**Alternatives considered:**
- Remove `dependencies.py` and inject raw `Session` / clients into routers directly — violates layered architecture.
- Exclude `dependencies.py` from the router contract — more complex configuration, achieves the same result.
- Use `allow_indirect_imports` — simplest, consistent with how the services/sqlalchemy contract is already handled in this project.

**Consequences:**
A router could import `dependencies.py` which imports repositories without triggering the contract. However, this is the intended usage pattern (routers must import deps to get their `Annotated` aliases). Direct repository imports from routers are still caught.

---

## 2026-04-16 — Wikipedia MediaWiki Action API + Wikidata SPARQL (dual source)

**Status:** accepted

**Context:**
The brief says "use the Wikipedia APIs" to fetch museum data. The canonical source
is the Wikipedia page `List_of_most_visited_museums`, which is a rendered HTML
table — not a stable structured source. Wikidata is the structured backbone of
Wikipedia and exposes exactly the fields we need (visitor counts, city, QID) via
SPARQL.

**Decision:**
Use the MediaWiki Action API (`action=parse`, `prop=wikitext`) to fetch and parse
the canonical museum list via `mwparserfromhell`. Use the Wikidata Query Service
(SPARQL) for structured enrichment (P1174 visitor records, P1082 city populations).

**Alternatives considered:**
- HTML scrape of the Wikipedia page: fragile to layout changes; not a stable API.
- Wikidata-only with a pre-filter on `P1174 > 2M visitors`: bypasses the Wikipedia
  sourcing requirement in the brief; the canonical list isn't perfectly reconstructible
  from Wikidata alone.

**Consequences:**
Two API surfaces to maintain. Both are rate-limited and occasionally flaky —
handled via tenacity retry with exponential backoff. The dual-source approach
directly answers the brief's spirit while keeping the pipeline defensible.

---

## 2026-04-16 — PostgreSQL over SQLite

**Status:** accepted

**Context:**
The dataset is small (~70 museums, ~70 cities). SQLite would be adequate for an
MVP and would eliminate the database container.

**Decision:**
PostgreSQL 16 via Docker Compose. SQLAlchemy 2.0 async + asyncpg driver.

**Alternatives considered:**
- SQLite with `aiosqlite`: simpler setup, no extra container, adequate for the
  data volume.
- DuckDB: excellent for analytics but not a typical OLTP backend; poor async
  story.

**Consequences:**
One additional container in Docker Compose. The "could later scale" argument
holds without a schema migration. PostgreSQL-specific upsert syntax
(`ON CONFLICT DO UPDATE`) is used in repositories — a deliberate choice that
simplifies the ingestion logic at the cost of portability to SQLite.

---

## 2026-04-16 — Per-city OLS linear fit for year-level population interpolation

**Status:** accepted

**Context:**
Wikidata city population records are sparse and collected on irregular years
(census years, UN estimates). Museum visitor records use different years. A
direct year-match join would drop ~40% of museums.

**Decision:**
For each city with ≥ 2 population data points, fit `population ~ year` OLS using
`numpy.polyfit`. Estimate the population at the museum's visitor year from the
fit. For cities with exactly 1 data point, use that point if it is within ±2
years of the visitor year; otherwise skip the museum and log a warning.

**Alternatives considered:**
- Nearest-neighbor year match (no fit): drops ~40% of museums.
- National growth-rate extrapolation: introduces a second data source and
  conflates city-level trends with national averages.

**Consequences:**
Extrapolation risk when the visitor year is outside the range of the available
population data. This is flagged via `population_is_extrapolated` on every
harmonized row and visualized in the notebook. Museums skipped for insufficient
data are logged with museum ID, city ID, and reason.

---

## 2026-04-16 — Log-log linear regression (not raw linear)

**Status:** accepted

**Context:**
Both visitor counts and city populations are heavily right-skewed. The Louvre
(~9 M visitors, Paris ~2 M pop.) and the National Museum of China (~8 M visitors,
Beijing ~22 M pop.) dominate a raw linear fit and drive the residuals for
mid-sized museums to noise.

**Decision:**
Fit `log(visitors) ~ log(population_est)` via `sklearn.LinearRegression`.

**Alternatives considered:**
- Raw linear regression: dominated by outliers; coefficient has no intuitive
  interpretation per unit.
- Poisson regression: more principled for count data, but adds a dependency and
  complexity; the point of this project is a demo, not a prediction model.

**Consequences:**
The coefficient is interpretable as an elasticity ("a 1% increase in city
population is associated with a β% increase in museum visitors"). Log
transformation requires all inputs > 0 — enforced by `InsufficientDataError`
validation in `RegressionService._validate_rows`.

---

## 2026-04-16 — Explicit refresh with 24h cooldown

**Status:** accepted

**Context:**
Wikidata SPARQL is rate-limited and occasionally returns 429 or 5xx under load.
Running the ingestion automatically on every container restart would hammer
Wikidata and risk being blocked.

**Decision:**
`POST /refresh` is user-triggered. `RefreshStateRepository` records
`last_refresh_at` on success. If a refresh is requested within
`settings.refresh_cooldown_hours` (default 24), the endpoint raises
`RefreshCooldownError` → HTTP 429 with `Retry-After`. Pass `?force=true` to
bypass.

**Alternatives considered:**
- Cron refresh (background task on a schedule): requires a task queue or
  APScheduler; overengineered for a demo.
- Refresh on startup: see above — risks rate-limiting on every deploy.

**Consequences:**
First container start requires a manual `POST /refresh` call. The notebook
Cell 1 handles this transparently (it catches the 429 on subsequent runs).
The `force=true` flag is documented in the README for the "Wikidata 429"
troubleshooting case.

---

## 2026-04-16 — Notebook calls API, never DB

**Status:** accepted

**Context:**
The brief asks the notebook to "programmatically use your other code." The
two interpretations are: (a) import the service classes directly, or (b) call
the HTTP endpoints.

**Decision:**
The notebook uses `requests` to call the FastAPI endpoints exclusively. No
direct database connection, no service imports.

**Alternatives considered:**
- Import `HarmonizationService` and `RegressionService` directly into the
  notebook: couples the notebook to the Python package; breaks if the API
  container is the target runtime.
- Notebook reads PostgreSQL via psycopg2/asyncpg: bypasses the API entirely,
  makes the service layer a demo-only decoration.

**Consequences:**
The notebook is a clean API consumer — it validates the full stack end-to-end
and remains portable to any environment where the API is reachable. The
`MUSEUMS_API_URL` environment variable (default `http://api:8000`) lets the
notebook work both in Docker Compose and against a local dev server.

---

## 2026-04-16 — IngestionWorkflow is a workflow, not a service

**Status:** accepted

**Context:**
`CLAUDE.md` forbids services from holding `AsyncSession` or calling `commit()`.
The ingestion pipeline must coordinate five repositories (museums, cities,
visitor records, population records, refresh state) and wrap them in a single
all-or-nothing transaction. No existing layer rule permits a service to do this.

**Decision:**
Place the ingestion orchestrator under `workflows/ingestion_workflow.py`. The
workflow layer is the one explicitly allowed to own `AsyncSession` and call
`session.commit()` / `session.rollback()`.

**Alternatives considered:**
- Keep ingestion as a service with a documented exception to the session rule:
  erodes the import-linter contracts and sets a precedent for bypassing the
  layering.
- Introduce a full Unit-of-Work abstraction: over-engineered for a single
  workflow; YAGNI.

**Consequences:**
One extra layer appears in the project structure. The `import-linter` contract
`Services cannot import AsyncSession` continues to hold cleanly. The workflow
is wired in `dependencies.py` and injected into the router via `IngestionWorkflowDep`.

---

## 2026-04-16 — RegressionService depends on HarmonizationService (documented exception)

**Status:** accepted

**Context:**
The python-fastapi guidelines prefer services to depend only on repositories.
`RegressionService` needs the harmonized dataset, which `HarmonizationService`
produces. Re-implementing the harmonization logic inside `RegressionService`
would duplicate 100+ lines.

**Decision:**
`RegressionService` takes `HarmonizationService` as a constructor argument and
calls `build_harmonized_rows()` as its input step. The dependency is documented
with a comment in `regression_service.py`.

**Alternatives considered:**
- Router calls both services sequentially and passes harmonization output into
  regression: leaks orchestration logic into the HTTP layer.
- Introduce a `RegressionWorkflow` that glues them: adds a layer for a two-step
  pipeline; overhead not justified at this scale.

**Consequences:**
One documented service-to-service edge. The `import-linter` services contract
does not forbid service-to-service imports (only session/router/workflow/client
imports are forbidden). Easy to split into a workflow if regression gains
additional inputs in the future.
