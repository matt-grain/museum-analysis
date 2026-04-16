# Implementation Status — Museums Analysis

**Last updated:** 2026-04-16
**Plan:** `IMPLEMENTATION_PLAN.md` + per-phase files
**Remote:** https://github.com/matt-grain/museum-analysis

## Progress Summary

| Phase | Status | Tasks | Completion |
|---|---|---|---|
| Phase 1: Foundation & infra (+ pre-commit) | ✅ Complete | 1/1 | 100% |
| Phase 2: Data layer (models, repos, migration) | ✅ Complete | 1/1 | 100% |
| Phase 3: External clients + ingestion workflow | ✅ Complete | 1/1 | 100% |
| Phase 4: Harmonization + regression services | ✅ Complete | 1/1 | 100% |
| Phase 5: API layer (schemas, query services, routers, main) | ⏳ Pending | 0/1 | 0% |
| Phase 6: Notebook + CI + docs | ⏳ Pending | 0/1 | 0% |

**Overall:** 4/6 phases complete (67%).

---

## Phase 1 — Foundation & Infra (+ pre-commit)

**Implemented:** 2026-04-16
**Agent:** `python-fastapi` (Sonnet)
**Tooling:** ✅ All pass — 11/11 tests, pyright clean, ruff clean, import-linter 5/5 contracts kept, radon + vulture + 4 custom hooks all green

### Completed
- ✅ Project scaffold: `pyproject.toml` (uv-managed, 5 import-linter contracts, pyright strict, ruff with ~16 rule selections), `.env.example`, `README.md`
- ✅ Core modules: `src/museums/{config,exceptions,logging_config,http_client,main}.py` (6 files, all under 65 lines)
- ✅ Alembic scaffold: `alembic.ini`, `alembic/env.py` (async mode, with Phase 2 TODO marker on line 20), `alembic/script.py.mako`
- ✅ Docker stack: `docker/{Dockerfile.api,Dockerfile.notebook,docker-compose.yml}` — postgres-16 + api + jupyter services
- ✅ Pre-commit pipeline: `.pre-commit-config.yaml` (ruff + pyright on commit; pytest + import-linter + radon + vulture + 4 custom hooks on push)
- ✅ Custom architectural hooks: `tools/pre_commit_checks/{_base,check_file_length,check_datetime_patterns,check_no_httpexception_outside_handlers,check_no_sync_http_in_src}.py`
- ✅ Tests: 4 config + 3 exceptions + 4 http_client = 11 tests, all passing

### Files Created (25 source files)
- `src/museums/__init__.py` (1)
- `src/museums/config.py` (38)
- `src/museums/exceptions.py` (62)
- `src/museums/http_client.py` (49)
- `src/museums/logging_config.py` (63)
- `src/museums/main.py` (47)
- `src/museums/{clients,repositories,routers,services,workflows}/__init__.py` (5 empty package markers — minor scope creep, Phase 2+ placeholders)
- `tests/{conftest.py,test_config.py,test_exceptions.py,test_http_client.py,__init__.py}`
- `tools/pre_commit_checks/{_base.py,check_file_length.py,check_datetime_patterns.py,check_no_httpexception_outside_handlers.py,check_no_sync_http_in_src.py,__init__.py}`
- `alembic/{env.py,script.py.mako}` + `alembic.ini`
- `docker/{Dockerfile.api,Dockerfile.notebook,docker-compose.yml}`
- `pyproject.toml`, `uv.toml`, `pyrightconfig.json`, `.pre-commit-config.yaml`, `.env.example`, `.gitignore`, `README.md`
- `tools/vulture_whitelist.py` (added during gate fix — legitimate whitelist for `app` / `lifespan` seen as unused by vulture but consumed by uvicorn)

### Out-of-plan additions (scope creep — all defensible)
- `pyrightconfig.json` + `uv.toml` — resolve the shared-venv + workspace-root issues specific to Matt's dev setup
- 5 empty subpackage `__init__.py` files — Phase 2-6 placeholders
- `tools/vulture_whitelist.py` — suppresses false positives for framework entry points

### Gate Fixes Applied During /check
1. `_base.py`: added `list[Path]` annotation to `files = []` (pyright strict compliance)
2. `pyrightconfig.json` + `[tool.pyright]` in `pyproject.toml`: added `include = ["src", "tests", "tools"]` and `exclude = ["prototype", "notebook", ...]` to prevent pyright from walking into parent workspace
3. `.pre-commit-config.yaml`:
   - Bumped `ruff-pre-commit` rev from `v0.7.0` to `v0.15.5` (match project dep)
   - All `uv run` → `uv run --no-sync` (prevent shared-venv file-lock race on `jobhunt.exe`)
   - `pyright` hook now uses `uv run --no-sync pyright .` (explicit cwd, avoids walking to parent pyright config)
   - `vulture` hook now consumes `tools/vulture_whitelist.py`
4. `git init` inside `homework/` — detached the project from the parent monorepo so pre-commit resolves the right git root

### Verification Checklist
| Item | Status |
|---|---|
| All planned files created | ✅ |
| Tooling gate fully green (both stages) | ✅ |
| Tests pass | ✅ 11/11 |
| Import-linter contracts | ✅ 5 kept / 0 broken |
| No `TODO`/`FIXME` without tracker ref | ✅ (one intentional `TODO Phase 2` in `alembic/env.py` line 20) |
| All `.py` files under 200 lines | ✅ (biggest: 102) |
| `ARCHITECTURE.md` updated | N/A (created in Phase 6 per plan) |
| `decisions.md` updated | N/A (created in Phase 6 per plan) |

---

---

## Phase 2 — Data Layer

**Implemented:** 2026-04-16
**Agent:** `python-fastapi` (Sonnet)
**Tooling:** ✅ All pass — 19/19 cumulative tests green, full pre-commit pipeline (both stages)

### Completed
- ✅ 5 SQLAlchemy 2.0 async models in `src/museums/models/`: `Base` + `TimestampMixin`, `City`, `Museum`, `VisitorRecord`, `PopulationRecord`, `RefreshState`
- ✅ 5 repositories in `src/museums/repositories/`: `CityRepository`, `MuseumRepository`, `VisitorRecordRepository`, `PopulationRecordRepository`, `RefreshStateRepository` — all using `sqlalchemy.dialects.postgresql.insert.on_conflict_do_update` for natural-key upserts
- ✅ Initial Alembic migration `alembic/versions/0001_initial.py` — 101 lines, autogenerated then manually reviewed (all CheckConstraints present, FK `ondelete` modes correct, FK-column indexes present)
- ✅ `alembic/env.py` — Phase 2 TODO removed; `target_metadata = Base.metadata`
- ✅ `tests/factories.py` — async factories (`build_city`, `build_museum`, `build_visitor_record`, `build_population_record`), all using `session.flush()` not `commit()`
- ✅ `tests/conftest.py` extended — `async_engine` (session-scoped, drops+creates schema) + `db_session` (function-scoped, rolls back after each test)
- ✅ 8 repository tests: 3 city + 3 museum + 2 refresh_state, all passing against a real `museums_test` Postgres DB

### Out-of-plan additions (scope creep — all defensible)
- `docker/docker-compose.dev.yml` — minimal override exposing port 5432 for local migration/test runs (the base compose file keeps the db on the Docker internal network). Reasonable — the Phase 1 spec didn't explicitly expose the port.
- `[tool.pytest.ini_options]` additions: `asyncio_default_fixture_loop_scope = "session"` + `asyncio_default_test_loop_scope = "session"` — required by pytest-asyncio 1.x to share the async engine across session + function fixtures.
- `upsert_by_name` in `museum_repository.py` calls `session.refresh(row)` after `ON CONFLICT DO UPDATE` — works around SQLAlchemy identity-map staleness on same-session re-upsert.

### Files Created (7 new)
- `src/museums/models/{base,city,museum,visitor_record,population_record,refresh_state}.py` (6 files)
- `src/museums/models/__init__.py`
- `src/museums/repositories/{city,museum,visitor_record,population_record,refresh_state}_repository.py` (5 files)
- `alembic/versions/0001_initial.py` (101 lines — exempt from length limit)
- `tests/factories.py` (73 lines)
- `tests/test_repositories/{__init__,test_city_repository,test_museum_repository,test_refresh_state_repository}.py` (4 files, 182 lines total)
- `docker/docker-compose.dev.yml` (override for local port exposure)

### Files Modified (3)
- `alembic/env.py` — removed Phase 2 TODO, wired `Base.metadata`
- `src/museums/repositories/__init__.py` — re-exports all 5 repositories
- `tests/conftest.py` — added `async_engine` + `db_session` fixtures
- `pyproject.toml` — `asyncio_default_*_loop_scope = "session"` + `alembic/**/*.py = ["ERA001", "E402"]` ruff ignore

### Tests Added
- `test_city_repository.py` — 3 tests (upsert insert, upsert update, get returns None)
- `test_museum_repository.py` — 3 tests (upsert then update, paginated w/ total, eager-loads city)
- `test_refresh_state_repository.py` — 2 tests (auto-creates singleton, mark_refreshed updates timestamp)

### Verification Checklist
| Item | Status |
|---|---|
| All planned files created | ✅ |
| Tooling gate fully green (both stages) | ✅ |
| Tests pass | ✅ 19/19 cumulative |
| Import-linter contracts | ✅ 5 kept / 0 broken |
| Migration applies cleanly against Postgres | ✅ (both `museums` + `museums_test` DBs) |
| All `.py` files under 200 lines (migration exempt) | ✅ |
| No TODO/FIXME without tracker ref | ✅ |

---

---

## Phase 3 — External Clients + Ingestion Workflow

**Implemented:** 2026-04-16
**Agent:** `python-fastapi` (Sonnet)
**Tooling:** ✅ All pass — 30/30 cumulative tests green, full pre-commit pipeline (both stages)

### Completed
- ✅ `MediaWikiClient.fetch_museum_list()` — Wikipedia Action API (`action=parse&prop=wikitext`), `mwparserfromhell`-based table-row parsing with File:/Image:/Category: filtering and dedup by case-insensitive title
- ✅ `WikidataClient.fetch_museum_enrichment(titles)` + `.fetch_city_populations(city_qids)` — SPARQL via `schema:about` title→QID resolver (no federated SERVICE clause), 50-QID batching, P1174/P585/P1082 property handling
- ✅ `IngestionWorkflow` under `workflows/` — 5-arg constructor `(mediawiki, wikidata, session, settings, deps: IngestionDeps)` with `IngestionDeps` as a frozen slotted dataclass holding the 5 repos; owns `session.commit()` / `rollback()`
- ✅ Retry/backoff via `tenacity` — `httpx.ConnectError`, `httpx.ReadTimeout`, `httpx.WriteTimeout`, and HTTP 429/5xx; every external call wrapped with domain-exception re-raise (`MediaWikiUnavailableError`, `WikidataUnavailableError`, `ExternalDataParseError`) preserving `__cause__`
- ✅ 11 new tests: 3 MediaWiki (happy + retry-succeed + retry-exhausted), 3 Wikidata (enrichment parse + population grouping + parse-error), 5 workflow (happy, cooldown blocks, force override, rollback on client failure, idempotent re-run)
- ✅ 3 realistic test fixtures: `wikitext_fixture.txt` (11 museum rows), `wikidata_museum_enrichment.json`, `wikidata_city_populations.json`

### Out-of-plan additions (all defensible)
- `tests/test_workflows/conftest.py` — separate `workflow_session` fixture that does NOT wrap tests in an outer transaction, so `session.commit()` inside the workflow doesn't collide with the `db_session` rollback pattern. Teardown does `TRUNCATE ... RESTART IDENTITY CASCADE` for isolation. Documented in the subagent report.
- `_parse_enrichments` and helpers extracted to module-level functions in `wikidata_client.py` — needed to keep the `WikidataClient` class under the 150-line limit and the parsing function under 30 lines.
- Test fixture has 11 museum rows instead of the plan's ≥ 3 — the client has a `_MIN_EXPECTED_ENTRIES = 10` guard (per CLAUDE.md "never silently drop data") so the fixture had to clear it. Reasonable.

### Files Created (13 new + 2 modified)
- `src/museums/clients/__init__.py` (modified — re-exports 17 lines)
- `src/museums/clients/mediawiki_client.py` (115 lines)
- `src/museums/clients/wikidata_client.py` (196 lines)
- `src/museums/workflows/__init__.py` (modified — 9 lines)
- `src/museums/workflows/ingestion_workflow.py` (167 lines)
- `tests/fixtures/__init__.py`
- `tests/fixtures/wikitext_fixture.txt` (18 lines, 11 museum rows)
- `tests/fixtures/wikidata_museum_enrichment.json` (56 lines)
- `tests/fixtures/wikidata_city_populations.json` (34 lines)
- `tests/test_clients/__init__.py`
- `tests/test_clients/test_mediawiki_client.py` (72 lines, 3 tests)
- `tests/test_clients/test_wikidata_client.py` (93 lines, 3 tests)
- `tests/test_services/__init__.py` (empty, reserved for Phase 4)
- `tests/test_workflows/__init__.py`
- `tests/test_workflows/conftest.py` (27 lines)
- `tests/test_workflows/test_ingestion_workflow.py` (209 lines, 5 tests)

### Verification Checklist
| Item | Status |
|---|---|
| All planned files created | ✅ |
| Tooling gate fully green (both stages) | ✅ |
| Tests pass | ✅ 30/30 cumulative |
| Import-linter contracts | ✅ 5 kept / 0 broken (client-layer contract 5 specifically validated) |
| Domain exception wrapping (no raw `httpx.*` escaping) | ✅ |
| SPARQL `schema:about` resolver (no federated SERVICE) | ✅ |
| `mwparserfromhell` used (no regex over wikitext) | ✅ |
| `IngestionWorkflow.__init__` exactly 5 args | ✅ |
| `IngestionDeps` is `@dataclass(slots=True, frozen=True)` | ✅ |
| All `.py` files under 200 lines | ✅ (biggest: `wikidata_client.py` at 196, `test_ingestion_workflow.py` at 209 — test file within the 300-line allowance) |

---

---

## Phase 4 — Harmonization + Regression Services

**Implemented:** 2026-04-16
**Agent:** `python-fastapi` (Sonnet)
**Tooling:** ✅ All pass — 43/43 cumulative tests green, full pre-commit pipeline (both stages)

### Completed
- ✅ `HarmonizationService` — per-city OLS `population ~ year` fit via `numpy.polyfit` (degree 1); ≥ 2 population-records required for fit, single-point fallback within ±2 years, skip otherwise with WARNING log; museum visitor-record selection by `(-year, -visitors)` sort (nearest-to-today, tie-break on max visitors); extrapolation flag set when visitor year outside fit range
- ✅ `RegressionService` — log-log `LinearRegression.fit()` via sklearn; raises `InsufficientDataError` when fewer than 5 harmonized rows or any non-positive values; returns `RegressionResult` with coefficient (elasticity), intercept, R², `n_samples`, `fitted_at` (tz-aware), and per-row `RegressionPoint` with residuals
- ✅ 13 new tests: 8 harmonization (real Postgres via `db_session` + factories) + 5 regression (pure in-memory via `_FakeHarmonization` stub)

### Design decisions (Sonnet's notes, all sound)
1. **`allow_indirect_imports = "True"`** added to the "Services cannot import sqlalchemy" import-linter contract. Without it, the contract forbade transitive imports through repositories — which would block services from consuming repos at all. This narrows the rule to its stated purpose: direct `from sqlalchemy import ...` in service files only. Documented in-place in `pyproject.toml`.
2. **sklearn typing via `Any`-annotated instance** — sklearn stubs are incomplete; annotating `LinearRegression()` as `Any` lets pyright accept `.fit()` / `.score()` / `.predict()` / `.coef_` / `.intercept_`. Return values cast explicitly with `float(...)` to narrow back to concrete types.
3. **`_FitResult(frozen=True)` dataclass** in `regression_service.py` — cleaner than a 3-tuple with mixed `Any`/float members when passing model coefficients between helpers.
4. **`InsufficientDataError` scoped to regression only, not harmonization** — the plan's "raise if non-empty input, empty output" wording conflicted with the test spec expecting `[]` silently when museums are skipped. Sonnet followed the tests (more specific). The empty-result → 422 mapping belongs in Phase 5's exception handler.

### Files Created (4 new + 1 modified)
- `src/museums/services/harmonization_service.py` (172 lines)
- `src/museums/services/regression_service.py` (123 lines)
- `tests/test_services/test_harmonization_service.py` (164 lines, 8 tests)
- `tests/test_services/test_regression_service.py` (123 lines, 5 tests)
- `pyproject.toml` — one-line `allow_indirect_imports = "True"` addition on the sqlalchemy contract (with updated justification comment)

### Verification Checklist
| Item | Status |
|---|---|
| All planned files created | ✅ |
| Tooling gate fully green (both stages) | ✅ |
| Tests pass | ✅ 43/43 cumulative |
| Import-linter contracts | ✅ 5 kept / 0 broken |
| Service-to-service dependency (Regression → Harmonization) documented | ✅ (goes in `decisions.md` in Phase 6) |
| All `.py` files under 200 lines | ✅ (biggest: `harmonization_service.py` at 172) |
| No TODO/FIXME without tracker ref | ✅ |

---

## Next Phase Preview

**Phase 5: API layer (schemas, query services, routers, main)**
- ~22 files new: 7 schemas + 2 query services (MuseumQueryService + CityQueryService to keep routers off repositories) + 6 routers + dependencies.py + main.py completion + 7 test files
- Dependencies: Phase 3 ✅ AND Phase 4 ✅
- Ready to start.
- Key outputs: full HTTP surface (`/health`, `POST /refresh`, `GET /museums`, `GET /cities/populations`, `GET /harmonized`, `GET /regression`), Pydantic response schemas, DI chains, global exception handlers mapping domain errors → HTTP status codes.
- Blocks: Phase 6 (notebook calls the API).

---

## Gaps Requiring Attention

None blocking. The minor scope-creep items above (empty `__init__.py` placeholders) are harmless and will be populated by Phase 2-6 as specified.
