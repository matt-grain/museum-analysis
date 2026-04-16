# Implementation Status — Museums Analysis

**Last updated:** 2026-04-16
**Plan:** `IMPLEMENTATION_PLAN.md` + per-phase files
**Remote:** https://github.com/matt-grain/museum-analysis

## Progress Summary

| Phase | Status | Tasks | Completion |
|---|---|---|---|
| Phase 1: Foundation & infra (+ pre-commit) | ✅ Complete | 1/1 | 100% |
| Phase 2: Data layer (models, repos, migration) | ✅ Complete | 1/1 | 100% |
| Phase 3: External clients + ingestion workflow | ⏳ Pending | 0/1 | 0% |
| Phase 4: Harmonization + regression services | ⏳ Pending | 0/1 | 0% |
| Phase 5: API layer (schemas, query services, routers, main) | ⏳ Pending | 0/1 | 0% |
| Phase 6: Notebook + CI + docs | ⏳ Pending | 0/1 | 0% |

**Overall:** 2/6 phases complete (33%).

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

## Next Phase Preview

**Phase 3: External clients + ingestion workflow**
- ~10 files new (2 clients + 1 workflow + 4 tests + 3 fixtures)
- Dependencies: Phase 2 ✅
- Ready to start.
- Key outputs: `MediaWikiClient` (Action API + `mwparserfromhell`), `WikidataClient` (SPARQL via `schema:about` resolver), `IngestionWorkflow` (under `workflows/`, takes `IngestionDeps` dataclass, owns the session + transaction boundary), `respx`-backed client tests that exercise retry exhaustion + parse errors, real-DB workflow tests.
- Parallelizable with Phase 4 (disjoint files).
- Blocks: Phase 5 (routers need the workflow).

---

## Gaps Requiring Attention

None blocking. The minor scope-creep items above (empty `__init__.py` placeholders) are harmless and will be populated by Phase 2-6 as specified.
