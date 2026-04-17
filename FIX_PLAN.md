# Fix Plan — museum-analysis

**Date:** 2026-04-16
**Based on:** `REVIEW.md` dated 2026-04-16
**Project type:** Python/FastAPI

## Summary

| Phase | Fix Units | Files Affected | Estimated Effort |
|---|---|---|---|
| Phase 0 — Micro-fixes | 5 | 6 | Low (≤30 min) |
| Phase 1 — Structural | 9 | ~30 | Medium (~3 h) |
| Phase 2 — Architectural | 2 | ~8 | Higher (~2 h) |
| **Total** | **16** | **~40** | |

**Agents required:** `python-fastapi` (everything). Single-agent project.

**Scope decisions:**
- **Include** all 🔴 Critical findings.
- **Include** all 🟡 Warnings except 3 that are deferred (see "Deferred Items" at the bottom).
- **Fix tests in the same phase** as the code they cover — don't split.

---

## Phase 0 — Micro-fixes

### Fix Unit 0.1: Justify `# type: ignore[arg-type]` suppressions in `main.py`

- **Category:** Documentation & Cognitive Debt
- **Agent:** `python-fastapi`
- **Files:** `src/museums/main.py`
- **Violation pattern (Grep):** `# type: ignore\[arg-type\]` without a nearby comment explaining why
- **Expected after fix:** A single explanatory block comment above the six `add_exception_handler` lines; individual `# type: ignore[arg-type]` kept but covered by the block comment.
- **Reference example:** The `# type: ignore[import-untyped]` in `src/museums/clients/mediawiki_client.py` has a one-line adjacent reason comment — follow that style.
- **HOW TO FIX:**
  1. Open `src/museums/main.py`.
  2. Above the `application.add_exception_handler(...)` block (currently lines 70-75), insert a block comment:
     ```python
     # FastAPI's add_exception_handler() typestub expects type[Exception] but our
     # domain-error subclasses are correctly typed as DomainError descendants.
     # This is a known starlette/fastapi stub limitation; the runtime behavior is correct.
     ```
  3. Leave the six `# type: ignore[arg-type]` trailing comments on each line.

### Fix Unit 0.2: Rename `is_ext` → `is_extrapolated` + justify remaining `Any` annotations

- **Category:** Typing & Style
- **Agent:** `python-fastapi`
- **Files:** `src/museums/services/harmonization_service.py`, `src/museums/schemas/museum.py`
- **Violation patterns:**
  - `is_ext = visitor_year` (abbreviated boolean local)
  - `Any` annotations on `_build_rows(eligible: list[Any])`, `_process_museum(museum: Any)`, `_fit_city(... -> ... NDArray[Any])`, `_flatten_city_name(data: Any) -> Any`
- **Expected after fix:** `is_ext` renamed; four `Any` annotations each have an adjacent `#` comment explaining why.
- **HOW TO FIX:**
  1. In `harmonization_service.py` line 158: rename `is_ext` to `is_extrapolated` (and update the return tuple on line 159).
  2. In `harmonization_service.py` line 89 (`coeffs: npt.NDArray[Any]`): add an adjacent comment:
     ```python
     # np.polyfit returns float64 but its stub uses Any for the generic dtype.
     coeffs: npt.NDArray[Any] = np.polyfit(years, pops, deg=1)
     ```
  3. In `harmonization_service.py` lines 105 (`eligible: list[Any]`) and 118 (`museum: Any`): add a single shared block comment above `_build_rows`:
     ```python
     # Museum is imported under TYPE_CHECKING to keep this service out of the
     # SQLAlchemy import graph (enforced by import-linter). The runtime type is
     # the SQLAlchemy Museum model; we use Any rather than a forward ref because
     # pyright can't narrow a string annotation to a concrete class across the
     # TYPE_CHECKING boundary for list element types.
     ```
  4. In `schemas/museum.py` line 32 (`data: Any -> Any` on `_flatten_city_name`): add a single-line comment above the method:
     ```python
     # Pydantic model_validator(mode="before") receives raw pre-validation input
     # which can be either an ORM instance or a dict. Any is the documented type.
     ```

### Fix Unit 0.3: Remove unused `anyio_backend` fixture from `conftest.py`

- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files:** `tests/conftest.py`
- **Violation:** `anyio_backend` fixture is defined but `asyncio_mode = "auto"` is active in `pyproject.toml`; no test uses anyio.
- **Expected after fix:** Fixture removed; 63 tests still green.
- **HOW TO FIX:**
  1. Open `tests/conftest.py`.
  2. Delete the `anyio_backend` function/fixture at line 37-40 (and its surrounding blank lines).
  3. Run `uv run pytest -v` — all tests should still pass.

### Fix Unit 0.4: Add invariant comment to SPARQL `_museum_query`

- **Category:** Documentation & Cognitive Debt
- **Agent:** `python-fastapi`
- **Files:** `src/museums/clients/wikidata_client.py`
- **Violation:** f-string SPARQL with `titles` interpolated. Low-risk (`titles` sourced from MediaWiki API, never user input) but not documented.
- **HOW TO FIX:**
  1. Above the `_museum_query(self, titles: list[str]) -> str` method (around line 148), add a docstring note:
     ```python
     def _museum_query(self, titles: list[str]) -> str:
         """Build the museum-enrichment SPARQL query.

         SECURITY NOTE: `titles` are always sourced from the MediaWiki Action
         API response (via MediaWikiClient.fetch_museum_list), never from
         user HTTP input. We therefore accept the narrow SPARQL injection
         surface here; quotes are escaped via chr(34)/chr(92) as defense-in-depth.
         """
     ```

### Fix Unit 0.5: Extract hardcoded fixture data in workflow + regression tests to factories

- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files:** `tests/factories.py`, `tests/test_workflows/test_ingestion_workflow.py`, `tests/test_routers/test_regression.py`
- **Violation:** Module-level `_ENTRIES`, `_ENRICHMENTS`, `_POPULATIONS` in ingestion tests; `_MUSEUM_DATA` tuple list in regression router test.
- **HOW TO FIX:**
  1. In `tests/factories.py`, add 3 new factory functions (plain sync builders — these are not DB-backed):
     ```python
     def make_museum_list_entry(title: str = "Louvre") -> MuseumListEntry: ...
     def make_museum_enrichment(title: str = "Louvre", city_qid: str = "Q90", visitors: int = 8_900_000, year: int = 2019) -> MuseumEnrichment: ...
     def make_population_series(city_qid: str = "Q90", start_year: int = 2010, n: int = 5, base: int = 2_000_000) -> list[PopulationPoint]: ...
     ```
  2. In `test_ingestion_workflow.py`, replace `_ENTRIES` / `_ENRICHMENTS` / `_POPULATIONS` with factory calls inside each test function.
  3. In `test_regression.py`, replace the `_MUSEUM_DATA` tuple loop with a parametrized helper using existing `build_city` / `build_museum` / `build_visitor_record` / `build_population_record` async factories.

---

## Phase 1 — Structural

### Fix Unit 1.1: Create `src/museums/enums/` package + 3 StrEnums

- **Category:** State Management & Enums
- **Agent:** `python-fastapi`
- **Files to create:** `src/museums/enums/__init__.py`, `src/museums/enums/error_code.py`, `src/museums/enums/external_source.py`, `src/museums/enums/log_level.py`
- **Dependencies:** None. **Blocks:** Fix Units 1.2, 1.3, 1.4.
- **HOW TO FIX:**
  1. Create `src/museums/enums/__init__.py` re-exporting `ErrorCode`, `ExternalSource`, `LogLevel`.
  2. Create `src/museums/enums/error_code.py`:
     ```python
     from __future__ import annotations
     from enum import StrEnum

     class ErrorCode(StrEnum):
         NOT_FOUND = "not_found"
         REFRESH_COOLDOWN = "refresh_cooldown"
         EXTERNAL_UNAVAILABLE = "external_unavailable"
         EXTERNAL_PARSE_ERROR = "external_parse_error"
         INSUFFICIENT_DATA = "insufficient_data"
     ```
  3. Create `src/museums/enums/external_source.py`:
     ```python
     from __future__ import annotations
     from enum import StrEnum

     class ExternalSource(StrEnum):
         MEDIAWIKI = "mediawiki"
         WIKIDATA = "wikidata"
     ```
  4. Create `src/museums/enums/log_level.py`:
     ```python
     from __future__ import annotations
     from enum import StrEnum

     class LogLevel(StrEnum):
         DEBUG = "DEBUG"
         INFO = "INFO"
         WARNING = "WARNING"
         ERROR = "ERROR"
     ```

### Fix Unit 1.2: Retype `ErrorOut.code` + handler call sites to use `ErrorCode` enum

- **Category:** State Management & Enums
- **Agent:** `python-fastapi`
- **Dependencies:** **Requires Fix Unit 1.1.**
- **Files:** `src/museums/schemas/common.py`, `src/museums/exception_handlers.py`, `tests/test_routers/test_refresh.py`, `tests/test_routers/test_regression.py`
- **HOW TO FIX:**
  1. In `schemas/common.py`: change `ErrorOut.code: str` to `ErrorOut.code: ErrorCode`; add import.
  2. In `exception_handlers.py`: replace 6 raw string literals with `ErrorCode.NOT_FOUND`, `.REFRESH_COOLDOWN`, `.EXTERNAL_UNAVAILABLE` (×2), `.EXTERNAL_PARSE_ERROR`, `.INSUFFICIENT_DATA`.
  3. In test files: update assertions from `== "refresh_cooldown"` → `== ErrorCode.REFRESH_COOLDOWN` (StrEnum compares equal to its str value, so tests that compare against raw strings will also keep passing — pick whichever style is consistent).

### Fix Unit 1.3: Retype `source`/`service_name` to use `ExternalSource` enum

- **Category:** State Management & Enums
- **Agent:** `python-fastapi`
- **Dependencies:** **Requires Fix Unit 1.1.**
- **Files:** `src/museums/exceptions.py`, `src/museums/clients/mediawiki_client.py`, `src/museums/clients/wikidata_client.py`, `src/museums/exception_handlers.py`, `tests/test_exceptions.py`
- **HOW TO FIX:**
  1. In `exceptions.py`: type `ExternalServiceError.service_name: ExternalSource`; change `MediaWikiUnavailableError.service_name = ExternalSource.MEDIAWIKI`; change `WikidataUnavailableError.service_name = ExternalSource.WIKIDATA`.
  2. In `ExternalDataParseError.__init__`: change `source: str` → `source: ExternalSource`.
  3. In `clients/mediawiki_client.py` (lines 34, 90, 112): replace `source="mediawiki"` with `source=ExternalSource.MEDIAWIKI`.
  4. In `clients/wikidata_client.py` (lines 135, 139): replace `source="wikidata"` with `source=ExternalSource.WIKIDATA`.
  5. In `exception_handlers.py`: the `[service=mediawiki]` / `[service=wikidata]` string interpolations can use `.value` or rely on `StrEnum.__str__`.
  6. In `test_exceptions.py` lines 36-37: either compare against `ExternalSource.MEDIAWIKI` or leave raw-string (StrEnum equality works both ways).

### Fix Unit 1.4: Retype `Settings.log_level` to `LogLevel` enum

- **Category:** State Management & Enums
- **Agent:** `python-fastapi`
- **Dependencies:** **Requires Fix Unit 1.1.**
- **Files:** `src/museums/config.py`, `src/museums/logging_config.py`, `tests/test_config.py`
- **HOW TO FIX:**
  1. In `config.py`: change `log_level: str = Field(default="INFO", pattern="...")` to `log_level: LogLevel = LogLevel.INFO`.
  2. In `logging_config.py` (line 60): replace `getattr(logging, level.upper(), logging.INFO)` with a direct mapping: `logging.getLevelNamesMapping()[level.value]` OR a dict `{LogLevel.DEBUG: logging.DEBUG, ...}`. Drop the defensive fallback (enum makes the value trusted).
  3. In `test_config.py`: the `test_settings_rejects_invalid_log_level` test currently passes `log_level="TRACE"`. With the enum this now raises `ValidationError` for the same reason — test still passes. No change needed; verify green.

### Fix Unit 1.5: Wrap `/cities/populations` + `/harmonized` in paginated response schemas

- **Category:** Architecture & SoC (🔴 Critical — missing pagination)
- **Agent:** `python-fastapi`
- **Files:** `src/museums/schemas/city.py`, `src/museums/schemas/harmonized.py`, `src/museums/services/city_query_service.py`, `src/museums/services/harmonization_service.py`, `src/museums/routers/cities.py`, `src/museums/routers/harmonized.py`, `tests/test_routers/test_cities.py`, `tests/test_routers/test_harmonized.py`, `tests/test_services/test_city_query_service.py`
- **Violation pattern:** `response_model=list[X]` in router decorators.
- **HOW TO FIX:**
  1. In `schemas/city.py` add: `class PaginatedCitiesOut(BaseModel): items: list[CityPopulationsOut]; pagination: PaginationMeta`.
  2. In `schemas/harmonized.py` add: `class PaginatedHarmonizedOut(BaseModel): items: list[HarmonizedRowOut]; pagination: PaginationMeta`.
  3. In `services/city_query_service.py`: change `list_with_populations()` → `list_paginated(skip: int, limit: int) -> PaginatedCitiesOut`. Return a sliced view of `cities` and a `PaginationMeta(total=len(all_cities), skip=skip, limit=limit)`.
  4. In `services/harmonization_service.py`: add a `build_harmonized_paginated(skip: int, limit: int) -> PaginatedHarmonizedOut` wrapping `build_harmonized_rows()`. Slice in Python (small N). Keep the existing `build_harmonized_rows()` since `RegressionService` uses it.
  5. In `routers/cities.py` + `routers/harmonized.py`: change `response_model`, endpoint return type, and add `skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)` query params.
  6. Update 3 test files to assert the new `{items, pagination}` shape.

### Fix Unit 1.6: Extract `HealthService` — remove DB query from health router

- **Category:** Architecture & SoC (🔴 Critical)
- **Agent:** `python-fastapi`
- **Files to create:** `src/museums/services/health_service.py`
- **Files to modify:** `src/museums/routers/health.py`, `src/museums/dependencies.py`, `tests/test_routers/test_health.py`
- **HOW TO FIX:**
  1. Create `services/health_service.py`:
     ```python
     from __future__ import annotations
     from sqlalchemy import text
     from museums.repositories.health_repository import HealthRepository

     class HealthService:
         def __init__(self, repo: HealthRepository) -> None:
             self._repo = repo

         async def check(self) -> None:
             await self._repo.ping()
     ```
  2. Create `repositories/health_repository.py` with `HealthRepository.ping()` that runs `await self._session.execute(text("SELECT 1"))`. (This is still a repository even though no model is involved — the DB query belongs here.)
  3. In `routers/health.py`: inject `HealthServiceDep`, call `await service.check()`, return `HealthOut(status="ok")`. No `SessionDep` in the router anymore.
  4. In `dependencies.py`: add `get_health_repo`, `get_health_service`, and `HealthServiceDep` Annotated alias.
  5. In `test_routers/test_health.py`: the existing test still works (it hits the endpoint). No change needed unless the test was mocking the session directly.

### Fix Unit 1.7: Move `async_sessionmaker` into lifespan (once per app)

- **Category:** Architecture & SoC (🔴 Critical performance)
- **Agent:** `python-fastapi`
- **Files:** `src/museums/main.py`, `src/museums/dependencies.py`, `tests/conftest.py`
- **HOW TO FIX:**
  1. In `main.py` lifespan: after creating `engine`, also create `session_factory = async_sessionmaker(engine, expire_on_commit=False)` and store on `app.state.session_factory`.
  2. In `dependencies.py` `get_session()`: replace the per-request `async_sessionmaker(...)` call with `factory = request.app.state.session_factory`. Everything else (the `async with factory() as session:` block) stays the same.
  3. Update `conftest.py`'s `app_client` fixture if it creates a custom app — set `app.state.session_factory` to a test sessionmaker.

### Fix Unit 1.8: Replace `_estimate_population` 4-tuple return with `PopulationEstimate` dataclass

- **Category:** Typing & Style
- **Agent:** `python-fastapi`
- **Files:** `src/museums/services/harmonization_service.py`
- **HOW TO FIX:**
  1. At module level (near `CityFit`), add:
     ```python
     @dataclass(frozen=True)
     class _PopulationEstimate:
         pop_est: float | None
         is_extrapolated: bool
         slope: float | None
         intercept: float | None
     ```
  2. Refactor `_estimate_population` to return `_PopulationEstimate(...)` instead of a 4-tuple.
  3. Update `_process_museum` to unpack via attribute access: `estimate.pop_est`, `estimate.is_extrapolated`, etc.

### Fix Unit 1.9: Remove `session.flush()` from `RefreshStateRepository`

- **Category:** Architecture & SoC
- **Agent:** `python-fastapi`
- **Files:** `src/museums/repositories/refresh_state_repository.py`, `src/museums/workflows/ingestion_workflow.py`
- **HOW TO FIX:**
  1. In `refresh_state_repository.py`: remove both `await self._session.flush()` calls (lines ~26 and ~41).
  2. In `get()`: after `self._session.add(state)`, the workflow's outer `commit()` will persist. If the workflow needs the autogenerated `id=1` visible immediately, the caller (workflow) can flush — but here `id=1` is hardcoded so no flush is needed.
  3. In `mark_refreshed()`: after `update(...)`, no flush needed — rely on `session.commit()` in the workflow. The `return await self.get()` call at the end will see the updated row because it's the same session.
  4. The workflow already calls `session.commit()` at the end of `refresh()` — no change needed there.
  5. Run tests: `test_refresh_state_repository.py` may need an explicit flush in the test fixture if it asserts visibility mid-transaction.

### Fix Unit 1.10: Add 5 critical missing tests

- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files to create:** `tests/test_schemas/__init__.py`, `tests/test_schemas/test_museum_schema.py`, `tests/test_repositories/test_visitor_record_repository.py`, `tests/test_repositories/test_population_record_repository.py`, `tests/test_schemas/test_refresh_schema.py`
- **Files to modify:** `tests/test_routers/test_refresh.py` (add 2 tests), `tests/test_services/test_regression_service.py` (add 1 test)
- **HOW TO FIX:** Write the following tests (one per finding in REVIEW.md §4):

  **test_museum_schema.py (3 tests):**
  - `test_museum_out_flattens_city_name_from_orm_object_with_city`
  - `test_museum_out_returns_none_city_name_when_city_is_none`
  - `test_museum_out_passes_plain_dict_through`

  **test_visitor_record_repository.py (3 tests):** upsert insert, upsert update, list_for_museum ordering.

  **test_population_record_repository.py (4 tests):** upsert insert, upsert update, list_all_grouped grouping, empty input returns 0.

  **test_refresh_schema.py (2 tests):** `from_summary` duration computation (happy + zero-duration edge case).

  **test_refresh.py additions (2 tests):** `test_refresh_returns_404_when_not_found_error_raised`, `test_refresh_returns_502_when_external_parse_error_raised` (stubbing workflow to raise each error).

  **test_regression_service.py addition (1 test):** `test_fit_raises_insufficient_data_when_row_has_nonpositive_population` (build rows list with one `population_est=0` row, assert `InsufficientDataError`).

### Fix Unit 1.11: Add smaller test gaps

- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files to modify:** `tests/test_clients/test_wikidata_client.py`, `tests/test_workflows/test_ingestion_workflow.py`, `tests/test_routers/test_harmonized.py`, `tests/test_routers/test_museums.py`
- **HOW TO FIX:** Add these tests (one per test file):
  - `test_fetch_city_populations_raises_external_data_parse_error_on_bad_response` — mirrors the existing `fetch_museum_enrichment` error test.
  - `test_refresh_rolls_back_on_mediawiki_failure` — stub mediawiki to raise, assert no rows persisted.
  - `test_get_harmonized_returns_empty_list_when_no_data` — hit `/harmonized` with empty DB.
  - `test_list_museums_skip_offsets_results` + `test_list_museums_returns_empty_on_no_data`.

### Fix Unit 1.12: Add test for `population_parsing.parse_populations` + smoke test for `logging_config`

- **Category:** Testing
- **Agent:** `python-fastapi`
- **Files to create:** `tests/test_logging_config.py`
- **Files to modify:** `tests/test_clients/test_wikidata_client.py`
- **HOW TO FIX:**
  1. In `test_wikidata_client.py`: add `test_parse_populations_groups_by_qid_and_dedupes_to_min`, `test_parse_populations_skips_rows_missing_year_or_population`.
  2. Create `tests/test_logging_config.py` with a single smoke test: `test_setup_logging_configures_root_logger` — call `setup_logging(LogLevel.DEBUG)`, assert `logging.getLogger().level == logging.DEBUG`.

---

## Phase 2 — Architectural

### Fix Unit 2.1: Repository Protocols + IngestionDeps typed against abstractions

- **Category:** Architecture & SoC (🟡 Warning — dependency inversion)
- **Agent:** `python-fastapi`
- **Files to create:** `src/museums/repositories/protocols.py`
- **Files to modify:** `src/museums/workflows/ingestion_workflow.py`, `src/museums/repositories/*.py` (no code change — they already match the Protocol shape; just add an `@runtime_checkable` Protocol per repo in `protocols.py`)
- **HOW TO FIX:**
  1. Create `repositories/protocols.py` with 5 `@runtime_checkable Protocol` classes mirroring each repo's public interface (`CityRepositoryProtocol`, `MuseumRepositoryProtocol`, `VisitorRecordRepositoryProtocol`, `PopulationRecordRepositoryProtocol`, `RefreshStateRepositoryProtocol`).
  2. In `workflows/ingestion_workflow.py`: change `IngestionDeps` field types from concrete classes to the Protocol types. Use `TYPE_CHECKING`-only imports for the protocols if needed.
  3. Verify `import-linter` contracts still pass — workflows importing from `repositories` (for Protocols) is already allowed.

### Fix Unit 2.2 [DEFERRED — optional]: Eliminate `RegressionService → HarmonizationService` dep

- **Category:** Architecture & SoC
- **Status:** Deferred to Phase 3 — documented exception, low-priority refactor.

---

## Deferred Items (Phase 3 / not planned this cycle)

These items from REVIEW.md's migration plan are explicitly deferred:

| Item | Reason |
|---|---|
| Pre-commit hook: routers can't import `sqlalchemy.text` | Import-linter already forbids `sqlalchemy` in routers. Redundant. |
| Pre-commit hook: every `list[...]` router response must be `Paginated*` | Hard to express statically; covered by code review. |
| Rename `database_echo` → `database_echo_enabled` | Breaking env-var change; `echo` is the pydantic/sqlalchemy convention. Accept the exemption. |
| `HealthStatus` StrEnum instead of `Literal["ok"]` | Degenerate single-member case; Literal is fine. |
| Eliminate `RegressionService → HarmonizationService` dep (Fix Unit 2.2) | Documented exception in `decisions.md`; low-priority refactor. |
| SPARQL parameterization | Low risk (invariant documented in Fix Unit 0.4); full parameterization would require a different SPARQL client library. |

---

## Execution Notes

- **Total estimated effort:** ~5 hours spread across 16 fix units.
- **Recommended run order:** Phase 0 (all 5 micro-fixes in one batch) → Phase 1 (Fix Unit 1.1 first, then 1.2-1.4 in parallel, then the rest) → Phase 2 (1 unit).
- **After each fix unit:** run `uv run pre-commit run --hook-stage pre-push --all-files` to catch regressions.
- **After each phase:** run `/check` to verify the delta.
- **Cumulative test target after Phase 1:** ~78 tests (was 63 + ~15 new).
- Run `/fix-review` next to execute this plan. It will read this file and dispatch subagents in order.
