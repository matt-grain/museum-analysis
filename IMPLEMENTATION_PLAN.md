# Implementation Plan — Museum Visitors vs. City Population

**Date:** 2026-04-16
**Scope:** Full project per `docs/homework.md` + `docs/PROJECT.md`.
**Agent:** `python-fastapi` for all phases.
**Target:** ~50 tests, 6 phases, 1 compose file.

Read `CLAUDE.md` at the project root for all cross-cutting tech constraints
(stack, error handling, layering, tooling). Each phase file below is
self-contained — a subagent given only the phase file + `CLAUDE.md` must
have everything it needs.

## Phase summary

| # | Title | Files (new) | Agent | Depends on |
|---|---|---|---|---|
| 1 | Foundation & infra (+ pre-commit) | ~21 | python-fastapi | — |
| 2 | Data layer (models, repos, migration) | ~12 | python-fastapi | 1 |
| 3 | External clients + ingestion workflow | ~10 | python-fastapi | 2 |
| 4 | Harmonization + regression services | ~4 | python-fastapi | 2 |
| 5 | API layer (schemas, query services, routers, main) | ~22 | python-fastapi | 3 & 4 |
| 6 | Notebook + CI + docs | ~5 | python-fastapi | 5 |

## Dependency graph

```
Phase 1 (foundation)
    │
    ▼
Phase 2 (data layer)
    │
    ├──────────────┬──────────────┐
    ▼              ▼              │
Phase 3        Phase 4            │
(clients +     (harmonization +   │
 ingestion)     regression)       │
    │              │              │
    └──────┬───────┘              │
           ▼                      │
       Phase 5 (API layer)◀───────┘
           │
           ▼
       Phase 6 (notebook + docs)
```

Phases 3 and 4 are **parallelizable** after Phase 2 — they touch disjoint
files. Run them concurrently in separate Sonnet dispatches if wall-clock
matters.

## Cross-phase dependencies (what each phase produces for later phases)

### Phase 1 produces (consumed by all later phases):
- `src/museums/config.py` — `Settings` class with DB URL, cooldown hours,
  HTTP timeouts. Services and clients read these via `Depends()`.
- `src/museums/exceptions.py` — full domain exception hierarchy
  (`DomainError`, `NotFoundError`, `RefreshCooldownError`,
  `MediaWikiUnavailableError`, `WikidataUnavailableError`,
  `ExternalDataParseError`, `InsufficientDataError`).
- `src/museums/http_client.py` — `create_http_client()` factory with
  tenacity-wrapped methods and timeouts. Clients use this directly.
- `src/museums/logging_config.py` — `setup_logging()` called from
  `main.py` lifespan.
- `docker/docker-compose.yml` — postgres + api + notebook services.
- Alembic scaffolding (`alembic.ini`, `alembic/env.py`,
  `alembic/script.py.mako`) — Phase 2 adds the first version.
- `.pre-commit-config.yaml` + `tools/pre_commit_checks/*.py` — 4 custom
  architectural hooks (file length, datetime tz-awareness, no
  HTTPException outside handlers, no sync HTTP in src).

### Phase 2 produces (consumed by Phases 3, 4, 5):
- `src/museums/models/*.py` — `Museum`, `City`, `VisitorRecord`,
  `PopulationRecord`, `RefreshState`.
- `src/museums/repositories/*.py` — one per aggregate, returning ORM
  models.
- `alembic/versions/0001_initial.py` — initial DB schema.
- `tests/factories.py` — reusable test data factories for all entities.

### Phase 3 produces (consumed by Phase 5):
- `src/museums/clients/mediawiki_client.py` — `MediaWikiClient.fetch_museum_list()`.
- `src/museums/clients/wikidata_client.py` — `WikidataClient.fetch_museum_enrichment()`
  and `WikidataClient.fetch_city_populations()`.
- `src/museums/workflows/ingestion_workflow.py` —
  `IngestionWorkflow.refresh(*, force: bool) -> RefreshSummary`,
  composed via the `IngestionDeps` dataclass.

### Phase 4 produces (consumed by Phase 5):
- `src/museums/services/harmonization_service.py` —
  `HarmonizationService.build_harmonized_rows() -> list[HarmonizedRow]`.
- `src/museums/services/regression_service.py` —
  `RegressionService.fit() -> RegressionResult`.

### Phase 5 produces (consumed by Phase 6):
- Full HTTP surface: `/health`, `POST /refresh`, `GET /museums`,
  `GET /cities/populations`, `GET /harmonized`, `GET /regression`.
- `src/museums/main.py` complete with lifespan, router registration,
  exception handlers.

### Phase 6 produces:
- `notebook/regression_analysis.ipynb` — 3-act demo notebook calling the
  live API.
- `ARCHITECTURE.md` — structure, layers, data flow.
- `decisions.md` — ADRs for non-trivial choices.
- `README.md` — final run instructions.

## Global constraints (apply to every phase)

Enforced via `CLAUDE.md` at the project root. Subagents MUST:

1. Run the full tooling gate (`pyright`, `ruff`, `pytest`, `lint-imports`)
   before reporting a phase as complete.
2. Keep every file ≤ 200 lines, every function ≤ 30 lines.
3. Handle connection errors per `CLAUDE.md` §error-handling (tenacity,
   domain exceptions, no bare `httpx.*` escaping the client layer).
4. Never mix layers — routers don't import repos/models/clients, services
   don't import `Session`, repos don't import services.
5. Not introduce dependencies outside the fixed stack in `CLAUDE.md`.

## Next steps

1. Review per-phase files (`IMPLEMENTATION_PLAN_PHASE_1.md` through
   `IMPLEMENTATION_PLAN_PHASE_6.md`).
2. Run `/plan-validate` on the overall plan to catch spec gaps.
3. Dispatch Sonnet on Phase 1 via `/implement-phase 1`.
4. After each phase, verify tooling gate passes + spot-check 1-2 files
   before proceeding.
