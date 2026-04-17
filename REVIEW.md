# Architecture Review — museum-analysis

**Date:** 2026-04-16
**Last fixed:** 2026-04-16 — 55/56 scoped findings resolved, 12/13 migration plan items complete (1 deferred); see `REVIEW_VALIDATION.md` for the full audit.
**Project type:** Python/FastAPI (async, SQLAlchemy 2.0, Pydantic v2)
**Reviewed commits:** main @ `9db6b9c` (post-Phase 6 + QA fixes + notebook polish)

## Executive Summary

| Category | Original Conformance | Post-fix Conformance | Critical | Warnings | Info |
|---|---|---|---|---|---|
| Architecture & SoC | Medium | **High** (7/7 fixable resolved, 1 deferred) | 3 → 0 | 5 → 1 (deferred) | 12 |
| Typing & Style | High | **High** (all addressed) | 0 | 6 → 0 | 14 |
| State Management & Enums | Medium | **High** (4/4 fixable resolved, 1 deferred) | 0 | 5 → 1 (deferred) | 5 |
| Testing Quality | Medium | **High** (14/15 resolved, 1 partial) | 5 → 0 | 10 → 1 (partial) | 5 |
| Documentation & Cognitive Debt | High | **High** (all addressed) | 0 | 2 → 0 | 16 |

**Overall:** Solid. Clean tooling (pyright/ruff/import-linter all 0 errors), all 63 tests passing, full pre-commit pipeline with 4 custom architectural hooks, complete docs (ARCHITECTURE.md + 9 ADRs). The critical findings cluster on three themes: (1) **pagination gaps** on two list endpoints; (2) **health router bypassing the service layer** for its `SELECT 1`; (3) **error-handler integration tests missing** for 2 of the 6 handlers and validator-level gaps.

### Top Critical Findings

1. **Health router executes raw `session.execute(text("SELECT 1"))` inline** — the one place in `src/museums/routers/` that violates the "routers never touch DB" rule. (`routers/health.py:17`)
2. **`get_session()` in `dependencies.py` rebuilds `async_sessionmaker` on every request** — a latent performance defect; should live on `app.state`. (`dependencies.py:34-42`)
3. **`GET /cities/populations` and `GET /harmonized` return unbounded `list[T]`** — no pagination wrapper. If Wikidata's response grows, these responses grow linearly. (`routers/cities.py`, `routers/harmonized.py`)
4. **`NotFoundError` → 404 handler and `ExternalDataParseError` → 502 handler are never tested at the router integration level** — only the `RefreshCooldownError` and the two `*Unavailable` handlers are covered. Two of six handlers are end-to-end unverified.
5. **`MuseumOut._flatten_city_name` (the only custom Pydantic `@model_validator`) has no dedicated test** — its three branches (ORM with `.city`, ORM with `city=None`, plain dict passthrough) are only incidentally exercised via router integration.

## Detailed Findings

### 1. Architecture & Separation of Concerns

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|---|---|---|---|---|
| 🔴 | Health router executes raw DB query inline | `routers/health.py:17` | Routers handle HTTP only — no DB queries | Move `SELECT 1` behind a `HealthService.check()` method; inject via `Depends` |
| 🔴 | `get_session()` rebuilds `async_sessionmaker` per request | `dependencies.py:34-42` | Factory should live on `app.state` | Build once in lifespan; retrieve via `request.app.state.session_factory()` |
| 🔴 | `GET /cities/populations` returns unbounded `list[CityPopulationsOut]` | `routers/cities.py:15` | List endpoints must always paginate | Wrap in `PaginatedCitiesOut` matching `PaginatedMuseumsOut` pattern |
| 🟡 | `GET /harmonized` returns unbounded `list[HarmonizedRowOut]` | `routers/harmonized.py:13` | List endpoints must always paginate | Same wrapping; add `skip`/`limit` query params |
| 🟡 | `RefreshStateRepository.get/mark_refreshed` call `session.flush()` | `repositories/refresh_state_repository.py:25-26,41` | Repositories should not control transaction lifecycle | Let the workflow flush/commit; repos issue DML only |
| 🟡 | `IngestionWorkflow` imports concrete `*Repository` classes | `workflows/ingestion_workflow.py:16-20` | Workflows should depend on Protocols/ABCs | Define `Protocol` types per repo; type `IngestionDeps` against them |
| 🟡 | No `enums/` directory | `src/museums/` | Enums must live in `enums/` | Create `src/museums/enums/` for the closed-set values flagged below |
| 🟡 | `RegressionService → HarmonizationService` service-to-service dep | `services/regression_service.py:14` | Services should not depend on services | Already documented as an ADR exception; optionally extract a shared `HarmonizedRowBuilder` to remove the coupling |
| 🔵 | 12 additional items all green — see Agent 1 report in commit history | — | — | — |

### 2. Typing & Style

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|---|---|---|---|---|
| 🟡 | `museum: Any`, `eligible: list[Any]` without justification | `services/harmonization_service.py:105,118` | `Any` requires justifying comment | Add comment: *"Museum ORM type is TYPE_CHECKING-only to avoid SQLAlchemy at service layer"* |
| 🟡 | `npt.NDArray[Any]` on `coeffs` without justification | `services/harmonization_service.py:89` | `Any` requires justifying comment | Tighten to `npt.NDArray[np.floating[Any]]` + comment |
| 🟡 | `_flatten_city_name(data: Any) -> Any` without justification | `schemas/museum.py:32` | `Any` requires justifying comment | Add comment: *"Pydantic model_validator(mode='before') forces Any for raw pre-validation input"* |
| 🟡 | `_estimate_population` returns a positional 4-tuple | `services/harmonization_service.py:146-153` | Max-5-args / typed interfaces | Replace with `@dataclass(frozen=True) class PopulationEstimate` |
| 🟡 | `is_ext` abbreviated boolean local | `services/harmonization_service.py:158` | Boolean naming (`is_` + descriptive) | Rename to `is_extrapolated` |
| 🟡 | `database_echo: bool` lacks `is_/has_` prefix on a `BaseSettings` field | `config.py:17` | Boolean naming | Rename to `database_echo_enabled` OR document explicit exemption for pydantic-settings fields |
| 🔵 | 14 other rules checked green (no `== None`, no `type(x) ==`, no bare `except`, no `print()`, no `.format()`, no wildcard imports, all functions fully typed, 4 `# type: ignore` with good justifications, `from __future__ import annotations` everywhere) | — | — | — |

### 3. State Management & Enums

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|---|---|---|---|---|
| 🟡 | `ErrorOut.code: str` is a raw string across 5 closed-set values (`not_found`, `refresh_cooldown`, `external_unavailable`, `external_parse_error`, `insufficient_data`) | `schemas/common.py`, `exception_handlers.py`, 2 test files | Never use raw strings for fixed sets | `class ErrorCode(StrEnum)` in `enums/error_code.py`; re-type `ErrorOut.code: ErrorCode` |
| 🟡 | `ExternalDataParseError(source="mediawiki"\|"wikidata")` | `clients/mediawiki_client.py`, `clients/wikidata_client.py`, `exception_handlers.py` | Never use raw strings for fixed sets | `class ExternalSource(StrEnum)` |
| 🟡 | `ExternalServiceError.service_name = "mediawiki"\|"wikidata"` class-level raw strings | `exceptions.py:39,45` | Never use raw strings for fixed sets | Reuse the same `ExternalSource` enum |
| 🟡 | `Settings.log_level: str` validated only by regex pattern, used via `getattr(logging, level.upper())` | `config.py:31`, `logging_config.py:60` | Config fields with discrete values should be enums | `class LogLevel(StrEnum)`; drop the regex + `getattr` fallback |
| 🔵 | `HealthOut.status: Literal["ok"]` — acceptable as a degenerate single-member case; optional upgrade to `StrEnum` for consistency | `schemas/common.py:22` | Enums preferred | Low-priority |
| 🔵 | No `status`/`state` column on any model → no FSM required (project is read-heavy ingestion) | — | — | — |
| 🔵 | No raw-string comparisons (`== "active"`, etc.), no match/case over string literals | — | — | — |

### 4. Testing Quality

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|---|---|---|---|---|
| 🔴 | `NotFoundError` → 404 handler never exercised at router level | `tests/test_routers/` | Every exception handler needs integration coverage | Stub a service to raise `NotFoundError`; assert 404 + `code=="not_found"` |
| 🔴 | `ExternalDataParseError` → 502 handler never exercised at router level | `tests/test_routers/` | Every exception handler needs integration coverage | `test_refresh_returns_502_on_external_parse_error` |
| 🔴 | `MuseumOut._flatten_city_name` custom validator has no dedicated test | no `tests/test_schemas/` dir | Custom Pydantic validators must be tested | New `tests/test_schemas/test_museum_schema.py` with ORM-with-city, ORM-with-None-city, plain-dict branches |
| 🔴 | `visitor_record_repository.py` and `population_record_repository.py` have no test files | `tests/test_repositories/` | Test structure mirrors `src/` | Add tests for upsert + `list_all_grouped` grouping |
| 🔴 | `RegressionService` non-positive values error branch untested | `tests/test_services/test_regression_service.py`, `services/regression_service.py:72-76` | Boundary / error-path coverage | `test_fit_raises_insufficient_data_when_row_has_nonpositive_population` |
| 🟡 | `GET /harmonized` empty-data response untested | `tests/test_routers/test_harmonized.py` | Boundary coverage | `test_get_harmonized_returns_empty_list_when_no_data` |
| 🟡 | `GET /museums` `skip` offset + empty-DB untested | `tests/test_routers/test_museums.py` | Boundary coverage | 2 new tests |
| 🟡 | `WikidataClient.fetch_city_populations` has no parse-error unit test | `tests/test_clients/test_wikidata_client.py` | Happy + error path per public method | Mirror the existing `fetch_museum_enrichment` error-path test |
| 🟡 | `IngestionWorkflow` rollback tests only cover `WikidataUnavailableError` | `tests/test_workflows/test_ingestion_workflow.py` | Both external-failure paths needed | Add `test_refresh_rolls_back_on_mediawiki_failure` |
| 🟡 | `RefreshResultOut.from_summary` classmethod untested (duration edge cases) | no schema tests | Custom factory methods need unit tests | 1 direct test |
| 🟡 | `population_parsing.parse_populations` (public wrapper of `filter_scope_outliers`) has no test — only the filter sub-function is tested | `tests/test_clients/test_wikidata_client.py` | Public parsing function needs coverage | 3 tests (happy-path grouping, (city,year) dedup takes min, malformed rows skipped) |
| 🟡 | `logging_config.py` untested (both renderer branches + level propagation) | — | Test structure mirrors `src/` | Add a smoke test asserting `setup_logging("DEBUG")` configures root logger |
| 🟡 | `anyio_backend` fixture conflicts with `asyncio_mode = "auto"` in pyproject | `tests/conftest.py:37-40`, `pyproject.toml:99` | Clear pytest-asyncio usage | Remove fixture unless anyio is intentional |
| 🟡 | Inline module-level fixture data in `test_ingestion_workflow.py` (_ENTRIES, _ENRICHMENTS, _POPULATIONS) | `tests/test_workflows/test_ingestion_workflow.py:28-57` | Use factories — never hardcode | Extract to `factories.py` helpers |
| 🟡 | Hardcoded `_MUSEUM_DATA` list of tuples in router test | `tests/test_routers/test_regression.py:14-21` | Use factories | Drive via factory helpers |
| 🔵 | All 63 test names follow `test_<action>_<scenario>_<expected>` | — | — | — |
| 🔵 | All sampled tests use explicit `# Arrange / # Act / # Assert` | — | — | — |
| 🔵 | Factories + `httpx.AsyncClient(ASGITransport)` used correctly throughout | `tests/conftest.py`, `tests/factories.py` | — | — |

### 5. Documentation & Cognitive Debt

| Severity | Finding | File(s) | Rule Violated | Recommendation |
|---|---|---|---|---|
| 🟡 | 6 `# type: ignore[arg-type]` on `add_exception_handler()` calls lack justification comments | `main.py:70-75` | `# type: ignore` must have justification | Add one explanatory comment above the block: *"FastAPI's add_exception_handler stubs expect `type[Exception]` but our DomainError subclasses are correctly typed — known stub limitation"* |
| 🟡 | `wikidata_client.py` uses f-strings for SPARQL query construction with user-derived titles | `clients/wikidata_client.py:148-172` | No f-string SQL (rule intent) | Low risk: `titles` come from MediaWiki API not user input. Add an invariant comment asserting this. Long-term: parameterize via SPARQL `VALUES` with literals bound by the library. |
| 🔵 | `ARCHITECTURE.md` has all 7 required sections + real code extracts | `ARCHITECTURE.md` | — | — |
| 🔵 | `decisions.md` has 9 ADRs in correct format | `decisions.md` | — | — |
| 🔵 | No file > 200 lines, no function > 30 lines, no class > 150 lines (AST-verified) | `src/museums/` | — | — |
| 🔵 | No `utils.py`/`helpers.py` catch-all files | — | — | — |
| 🔵 | No `TODO`/`FIXME`/`HACK` anywhere in `src/` or `tests/` | — | — | — |
| 🔵 | `uv.lock` present and committed; no floating versions in `pyproject.toml` | — | — | — |
| 🔵 | No hardcoded secrets, no CORS wildcards, no sync blocking in async | — | — | — |
| 🔵 | Alembic configured, 1 migration applied | `alembic/` | — | — |
| 🔵 | `README.md` has CI badge + setup + troubleshooting | `README.md` | — | — |

## Migration Plan

### Phase 0 — Quick Wins (mechanical, low risk)

- [x] Add justification comments on 6 `# type: ignore[arg-type]` in `main.py:70-75` ✅
- [x] Rename `is_ext` → `is_extrapolated` in `harmonization_service.py:158` ✅
- [x] Add 3 justifying comments on `Any` annotations (harmonization_service, schemas/museum) ✅
- [x] Remove the unused `anyio_backend` fixture from `conftest.py` ✅
- [x] Add invariant comment in `_museum_query` asserting `titles` are API-sourced (no SPARQL-injection surface) ✅

### Phase 1 — Structural Improvements (medium effort)

- [x] Create `src/museums/enums/` with `ErrorCode`, `ExternalSource`, `LogLevel` StrEnums; retype the 5 call sites (`schemas/common.py`, `exception_handlers.py`, `exceptions.py`, `config.py`, `logging_config.py`, both clients) ✅
- [x] Wrap `GET /cities/populations` and `GET /harmonized` in paginated response schemas; push `skip`/`limit` into the corresponding services ✅
- [x] Extract a `HealthService.check()` to move the `SELECT 1` out of `routers/health.py` ✅
- [x] Move `async_sessionmaker` construction into the lifespan; store on `app.state`; simplify `get_session()` ✅
- [x] Replace the 4-tuple return in `_estimate_population` with a `@dataclass PopulationEstimate` ✅
- [x] Refactor `RefreshStateRepository` to remove `session.flush()` calls; let the workflow control transaction lifecycle ✅
- [x] Add missing tests (5 critical + 9 warning items covered — one item partial, see Testing section) ✅ — 23 new tests, 59→86 total

### Phase 2 — Architectural Changes (higher effort)

- [ ] Define repository `Protocol` types and type `IngestionDeps` against them (decouples workflow from concrete SQLAlchemy repos) — ⏭️ **Deferred** per FIX_PLAN.md (low-priority take-home scope)
- [ ] (Optional) Eliminate the `RegressionService → HarmonizationService` service-to-service dep by extracting a shared `HarmonizedRowBuilder` — ⏭️ **Deferred** (documented exception in decisions.md ADR #8)

### Phase 3 — Ongoing Discipline

- [x] Add a pre-commit hook asserting router files don't import `sqlalchemy.ext.asyncio.text` (would catch the health-router regression) ✅ — implemented as `check_no_sqlalchemy_in_routers` (bans all `sqlalchemy*` imports in routers)
- [ ] Add a pre-commit hook asserting every router endpoint returning `list[...]` is wrapped in a `Paginated*` schema — ⏭️ **Deferred** per FIX_PLAN.md (hard to express statically; covered by review)
- [ ] Enable import-linter contract: *"clients must not interpolate user input into SPARQL"* (harder — likely stays as a code-review rule) — ⏭️ **Deferred** (invariant now documented in `_museum_query` docstring)
