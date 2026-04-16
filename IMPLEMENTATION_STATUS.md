# Implementation Status — Museums Analysis

**Last updated:** 2026-04-16
**Plan:** `IMPLEMENTATION_PLAN.md` + per-phase files
**Remote:** https://github.com/matt-grain/museum-analysis

## Progress Summary

| Phase | Status | Tasks | Completion |
|---|---|---|---|
| Phase 1: Foundation & infra (+ pre-commit) | ✅ Complete | 1/1 | 100% |
| Phase 2: Data layer (models, repos, migration) | ⏳ Pending | 0/1 | 0% |
| Phase 3: External clients + ingestion workflow | ⏳ Pending | 0/1 | 0% |
| Phase 4: Harmonization + regression services | ⏳ Pending | 0/1 | 0% |
| Phase 5: API layer (schemas, query services, routers, main) | ⏳ Pending | 0/1 | 0% |
| Phase 6: Notebook + CI + docs | ⏳ Pending | 0/1 | 0% |

**Overall:** 1/6 phases complete (17%).

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

## Next Phase Preview

**Phase 2: Data layer (models, repos, migration)**
- ~12 files new
- Dependencies: Phase 1 ✅
- Ready to start.
- Key outputs: SQLAlchemy 2.0 async models (`Museum`, `City`, `VisitorRecord`, `PopulationRecord`, `RefreshState`), 5 repositories, initial Alembic migration (`0001_initial.py`), `tests/factories.py`, ~8 repository sanity tests.
- Blocks: Phase 3 (needs models + repos for ingestion) and Phase 4 (needs repos for harmonization).

---

## Gaps Requiring Attention

None blocking. The minor scope-creep items above (empty `__init__.py` placeholders) are harmless and will be populated by Phase 2-6 as specified.
