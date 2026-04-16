# Project Instructions — Museum Visitors vs. City Population

Read this before editing any file. The global rules in
`~/.claude/rules/python-fastapi/*.md` apply; this file adds project-specific
constraints on top.

Design rationale lives in `docs/PROJECT.md`. Read it for context about
*why* choices were made. This file is about *what* to do.

## Scope reminder

This is a **take-home interview project**, not a production system. Keep it
tight (~50 tests total, one `src/museums/` package). Do not over-engineer.
No FSMs (no stateful entities in this domain). No auth. No observability
stack beyond structured logs.

## Tech stack (fixed — do not substitute)

- **Python 3.13**, `uv` for dependency management.
- **FastAPI** async + **Pydantic v2**.
- **SQLAlchemy 2.0 async** + **Alembic** + **asyncpg** driver.
- **PostgreSQL 16** via docker-compose.
- **httpx** async for all external HTTP calls.
- **tenacity** for retry/backoff.
- **scikit-learn** for the regression (`LinearRegression`).
- **numpy** / **pandas** for the harmonization math.
- **pytest** + **pytest-asyncio** + **httpx ASGITransport** for tests.
- **Jupyter** (`jupyter/minimal-notebook` base image + installed deps).

Never add a dependency not listed here without updating `docs/PROJECT.md`
and `decisions.md`.

## Layered architecture (enforced)

```
routers/     → HTTP only (parse request, call service/workflow, return response_model)
workflows/   → multi-repo orchestration with explicit transaction boundaries
services/    → business logic (harmonization, regression, query services)
repositories/→ SQLAlchemy queries (the only layer that imports models/Session)
models/      → SQLAlchemy ORM (Mapped[] / mapped_column, SQLAlchemy 2.0 style)
schemas/     → Pydantic DTOs (Create / Out, separate per purpose)
clients/     → external API clients (MediaWiki, Wikidata) — raise domain errors
exceptions.py→ domain exception hierarchy + FastAPI handlers
dependencies.py → Depends() chains
```

Hard rules:

- **Routers never import models, repositories, or clients.** Router →
  service OR workflow only.
- **Services never touch `Session`** — take repositories as constructor
  args. Use a workflow when you need a session / transaction boundary.
- **Workflows MAY hold an `AsyncSession`** and coordinate multiple
  repositories/clients under one transaction. That is the one layer
  allowed to `session.commit()` / `rollback()`.
- **Services never raise `HTTPException`** — raise domain exceptions; the
  global handler maps them to HTTP status codes.
- **Repositories return ORM models**, services convert to schemas.
- **No sync blocking I/O** inside async handlers. No `requests`, no
  `time.sleep`, no sync DB drivers.

## Error handling — first-class

External API calls are **the** failure surface of this app. The brief calls
this out explicitly; so does the project spec. Requirements:

1. **Every external HTTP call goes through a shared `httpx.AsyncClient`**
   built in `http_client.py` and injected via `Depends()`.
2. **Retries with tenacity**: exponential backoff (1s, 2s, 4s), max 3
   attempts, retry only on:
   - `httpx.ConnectError`
   - `httpx.ReadTimeout` / `httpx.WriteTimeout`
   - HTTP 5xx responses
   - HTTP 429 (Too Many Requests)
   Do NOT retry on 4xx (client errors — our fault, fail loudly).
3. **Explicit timeouts** on the client: `timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)`.
4. **Client methods raise domain exceptions**, never bare `httpx.*`:
   - `MediaWikiUnavailableError` (retry exhausted or 5xx)
   - `WikidataUnavailableError` (retry exhausted or 5xx)
   - `ExternalDataParseError` (unexpected response shape)
5. **Global FastAPI exception handlers** map:
   - `MediaWikiUnavailableError` / `WikidataUnavailableError` → 503
   - `RefreshCooldownError` → 429 with `Retry-After` header
   - `NotFoundError` → 404
   - `InsufficientDataError` → 422
6. **DB startup check**: `main.py` lifespan runs `SELECT 1`; if it fails,
   log a clear error and let uvicorn exit non-zero. Do not silently
   continue.
7. **No bare `except:` or `except Exception:`** without re-raise or
   explicit domain mapping.

## Data & math

- **Population year extraction**: keep only `pq:P585` (point in time) years
  ≥ 2000.
- **Per-city OLS fit**: `population ~ year`, ≥ 2 points required. If a city
  has <2 points, skip interpolation and match the single point only if it's
  within ±2y of the museum visitor year; otherwise drop the museum from
  the harmonized set (log a warning).
- **Museum visitor record selection**: if a museum has multiple years,
  pick the one with the most recent `pq:P585`. Break ties by max visitor
  count.
- **Regression**: `log(visitors) ~ log(population_est)` via
  `sklearn.linear_model.LinearRegression`. Require ≥ 5 harmonized rows to
  fit (raise `InsufficientDataError` otherwise).
- **Never silently drop data** — log each drop with museum/city id and
  reason.

## Refresh policy

- `POST /refresh` writes a row to `refresh_state` on success.
- Before fetching, read `refresh_state.last_refresh_at`. If younger than
  `settings.refresh_cooldown_hours` (default 24), raise
  `RefreshCooldownError` unless `?force=true` is passed.
- Refresh is **all-or-nothing** in the DB: wrap ingestion in a single
  transaction; roll back on any client failure after N retries.

## File & function discipline

- Max 200 lines per file (excluding imports/docstrings).
- Max 30 lines per function. Extract helpers aggressively.
- Max 5 function arguments. Beyond that, pass a dataclass or Pydantic
  model.
- One public class per module in `services/`, `repositories/`, `clients/`.

## Testing

- Target ~50 tests total. Do not inflate.
- Pattern: `test_<action>_<scenario>_<expected>` naming.
- Arrange / Act / Assert with blank-line separation.
- Service unit tests use **repository fakes** (in-memory dicts), not mocks.
- Client tests use **`respx`** to stub httpx — test retry behavior
  explicitly.
- Router integration tests use `httpx.AsyncClient(transport=ASGITransport(app=app))`.
- Database tests use a separate `museums_test` DB (dropped + recreated
  per-session fixture).
- Every domain exception must be raised by at least one test.

## How to use the tools (important for subagents)

### `uv` — the ONLY package manager

- `uv` is the entry point for everything Python on this project. Never
  invoke `pip`, `poetry`, `pipenv`, `python -m venv`, or plain `python`
  for running project code.
- Add a runtime dependency: `uv add <package>`.
- Add a dev dependency: `uv add --dev <package>`.
- Remove a dependency: `uv remove <package>`.
- Install everything from the lockfile: `uv sync`. Do this after pulling
  a branch with new deps, or after editing `pyproject.toml`.
- Run any CLI tool installed in the project: `uv run <tool> [args]`.
  Examples:
  - `uv run pyright .`
  - `uv run ruff check . --fix`
  - `uv run ruff format .`
  - `uv run pytest -v`
  - `uv run pytest tests/test_http_client.py::test_should_retry_returns_true_for_5xx`
  - `uv run lint-imports` (runs import-linter against the contracts in `pyproject.toml`)
  - `uv run alembic upgrade head`
  - `uv run uvicorn museums.main:app --reload`
- Never edit `pyproject.toml` dependency pins by hand — use `uv add`
  with a version constraint (`uv add "pydantic>=2.6"`). The ONE exception
  is editing the `[tool.*]` sections (pyright, ruff, import-linter
  contracts, pytest) — those are project config, not deps.
- After `uv add` / `uv remove`, the lockfile (`uv.lock`) is updated
  automatically. Commit it alongside `pyproject.toml`.

### `import-linter` — layer-boundary enforcement

- Contracts live in `pyproject.toml` under `[[tool.importlinter.contracts]]`.
  See CLAUDE.md §"Tooling gate" for the exact list.
- Run locally: `uv run lint-imports`.
- When it fails, the output names the source module, the forbidden
  import, and the contract that was broken. Fix the import, don't edit
  the contract.
- Common failure: a router file imports a repository. Fix by routing
  through a service/workflow instead of the repo directly.

### `pre-commit` — two-stage hook pipeline

- Install hooks (both stages) once per clone:
  `uv run pre-commit install --install-hooks`.
  This wires up `.git/hooks/pre-commit` AND `.git/hooks/pre-push`.
- Run the fast stage against all files (ruff, pyright):
  `uv run pre-commit run --all-files`.
- Run the thorough stage (pytest, import-linter, radon, vulture, custom
  checks): `uv run pre-commit run --hook-stage pre-push --all-files`.
- If a hook fails, fix the underlying issue. Never bypass with
  `--no-verify`.

### `alembic` — migrations

- Generate a new migration after model changes:
  `uv run alembic revision --autogenerate -m "add foo column"`.
  Review the generated file before committing — autogenerate is not
  perfect (it sometimes drops `CheckConstraint` entries and indexes).
- Apply migrations: `uv run alembic upgrade head`.
- Downgrade one step: `uv run alembic downgrade -1`.

### `docker compose`

- Validate the compose file without starting: `docker compose config`.
- Build and start everything: `docker compose up --build`.
- Tail a service's logs: `docker compose logs -f api`.
- Stop and clean up: `docker compose down`. Add `-v` to wipe volumes.

## Tooling gate (run before asking Matt for /check)

```bash
uv sync
uv run pre-commit run --all-files
uv run pre-commit run --hook-stage pre-push --all-files
docker compose config
```

All must be green. Individual tools for debugging:

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest
uv run lint-imports
```

Pyright in **strict** mode. Ruff config in `pyproject.toml` uses the
selection listed in `~/.claude/rules/python-fastapi/tooling.md`.
Import-linter contracts:

1. Routers cannot import repositories, models, or clients.
2. Services cannot import routers, workflows, or clients.
3. Services cannot import `sqlalchemy.ext.asyncio.AsyncSession` (workflows own the session).
4. Repositories cannot import services, routers, workflows, or clients.
5. Clients cannot import anything from `src.museums` except `config`,
   `exceptions`, and `http_client`.

## What NOT to do

- Don't add auth, rate limiting middleware, or CORS configs — not in scope.
- Don't add caching layers (Redis, in-process) — the cooldown already
  solves the Wikidata rate-limit concern.
- Don't add Celery, RQ, or any task queue — `/refresh` is synchronous
  from the client's perspective (it awaits the ingestion).
- Don't create abstract base classes for repositories "in case we swap DB
  later" — YAGNI.
- Don't add `# type: ignore` or `# noqa` without a comment explaining why.
- Don't leave `TODO` / `FIXME` — either implement or flag as a gap in the
  phase completion report.
- Don't touch `prototype/` — it's reference-only exploration code.

## Commit discipline

- **No phase commits until Matt runs `/check`.** When a phase's tooling
  gate passes, STOP and wait for Matt's `/check` to sign off the phase.
  Only after `/check` returns green does a commit happen. Do not
  pre-emptively `git add` / `git commit` — Matt owns the commit gate.
- One logical change per commit. Refactors in separate commits from
  features.
- Commit messages: imperative present ("add", "fix", "refactor"), short
  summary line, body if needed.
- Never bypass pre-commit hooks. If a hook fails, fix the underlying
  issue.

## Documentation triggers

Update `docs/PROJECT.md` if scope or design changes. Append to
`decisions.md` if a non-trivial technical choice is made during
implementation (e.g., the per-city OLS fit threshold). Update
`ARCHITECTURE.md` once the skeleton is built (Phase 6).

## When in doubt

- Prefer deletion to abstraction.
- Prefer the simplest code that passes the tooling gate.
- Read `docs/PROJECT.md` for the *why*, read this file for the *what*,
  read `~/.claude/rules/python-fastapi/` for the *how*.
