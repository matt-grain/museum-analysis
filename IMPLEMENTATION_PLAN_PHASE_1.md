# Phase 1 — Foundation & Infrastructure

**Agent:** `python-fastapi`
**Depends on:** nothing
**Produces for later phases:** config, exceptions, http_client with
retry/backoff, logging, Docker Compose stack, Alembic scaffold.

Read `CLAUDE.md` and `docs/PROJECT.md` before starting.

## Files to create (new)

### `pyproject.toml` (REPLACE — existing file is a stub)
**Purpose:** Single source of truth for project metadata, dependencies, and
tooling config.
**Contents:**
- `[project]` — name `museums`, version `0.1.0`, Python `>=3.13`.
- Runtime deps: `fastapi`, `uvicorn[standard]`, `pydantic>=2.6`,
  `pydantic-settings`, `sqlalchemy[asyncio]>=2.0`, `asyncpg`, `alembic`,
  `httpx`, `tenacity`, `scikit-learn`, `numpy`, `pandas`, `structlog`,
  `mwparserfromhell` (structured parsing of MediaWiki wikitext — used by
  Phase 3's MediaWiki client).
- Dev deps: `pytest`, `pytest-asyncio`, `respx`, `pyright`, `ruff`,
  `import-linter`, `bandit`, `radon`, `vulture`, `pre-commit`.
- `[tool.pyright]` — `typeCheckingMode = "strict"`, `pythonVersion = "3.13"`.
- `[tool.ruff]` — `line-length = 120`, `target-version = "py313"`.
- `[tool.ruff.lint]` — selection per `~/.claude/rules/python-fastapi/tooling.md`.
- `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]`.
- `[tool.importlinter]` — `root_packages = ["src.museums"]`.
- `[[tool.importlinter.contracts]]` — 5 contracts per `CLAUDE.md` (note:
  routers/services/workflows/repos/clients). Implement contract 3
  ("Services cannot import `AsyncSession`") as a `forbidden` contract
  with `source_modules = ["src.museums.services"]` and
  `forbidden_modules = ["sqlalchemy.ext.asyncio.AsyncSession"]` — if
  import-linter cannot target a class attribute, use `forbidden_modules = ["sqlalchemy.ext.asyncio"]` and explicitly allow it via a
  comment in each legit use site (there should be none in services).
**Constraint:** Use `uv add` / `uv add --dev` to populate, never manual
pin edits except for bounds. Commit `uv.lock` alongside.

### `src/museums/__init__.py`
**Purpose:** Package marker.
**Contents:** Single line `"""Museums visitors vs. city population."""`.

### `src/museums/config.py`
**Purpose:** Centralized settings via `pydantic-settings`.
**Class:** `Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", env_prefix="MUSEUMS_")`.
**Fields:**
- `database_url: PostgresDsn` — e.g. `postgresql+asyncpg://museums:museums@db:5432/museums`.
- `database_echo: bool = False`.
- `refresh_cooldown_hours: int = Field(default=24, ge=1, le=168)`.
- `http_connect_timeout_seconds: float = 5.0`.
- `http_read_timeout_seconds: float = 30.0`.
- `http_max_retries: int = Field(default=3, ge=1, le=10)`.
- `mediawiki_base_url: HttpUrl = HttpUrl("https://en.wikipedia.org/w/api.php")`.
- `wikidata_sparql_url: HttpUrl = HttpUrl("https://query.wikidata.org/sparql")`.
- `wikipedia_list_page_title: str = "List_of_most_visited_museums"`.
- `museum_visitor_threshold: int = 2_000_000`.
- `log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")`.
- `user_agent: str = "MuseumsApp/0.1 (https://github.com/example/museums)"`.
**Factory:** `@lru_cache def get_settings() -> Settings: return Settings()`.
**Constraint:** Never read `os.environ` directly anywhere else in the
codebase. Always `settings = get_settings()` or inject via `Depends()`.

### `src/museums/exceptions.py`
**Purpose:** Domain exception hierarchy + helpers.
**Classes (in order):**
- `DomainError(Exception)` — base class.
- `NotFoundError(DomainError)` — `__init__(entity: str, identifier: str | int)`.
- `RefreshCooldownError(DomainError)` — `__init__(remaining_seconds: int)`;
  exposes `retry_after_seconds` attribute for the handler to read.
- `ExternalServiceError(DomainError)` — base for client failures, stores
  `service_name: str`.
- `MediaWikiUnavailableError(ExternalServiceError)` — `service_name = "mediawiki"`.
- `WikidataUnavailableError(ExternalServiceError)` — `service_name = "wikidata"`.
- `ExternalDataParseError(DomainError)` — stores `source: str` and `detail: str`.
- `InsufficientDataError(DomainError)` — `__init__(reason: str)`; used by
  regression service when fewer than 5 harmonized rows.
**Constraint:** No HTTP status codes here — that's the handler's job in
Phase 5. No `HTTPException` imports.

### `src/museums/logging_config.py`
**Purpose:** Structured logging setup for the app.
**Function:** `def setup_logging(level: str) -> None`.
**Contents:** Configure `structlog` with `TimeStamper`, `add_log_level`,
`JSONRenderer` (production) or `ConsoleRenderer` (if `stderr.isatty()`).
Bind stdlib logger so `httpx` / `sqlalchemy` logs also flow through.
**Constraint:** Call once from `main.py` lifespan on startup; never from
module top-level.

### `src/museums/http_client.py`
**Purpose:** Shared `httpx.AsyncClient` factory with tenacity-decorated
methods; the ONE place retry/backoff logic lives.
**Functions:**
- `def build_timeout(settings: Settings) -> httpx.Timeout` — returns
  `httpx.Timeout(connect=..., read=..., write=10.0, pool=5.0)`.
- `@asynccontextmanager async def http_client_lifespan(settings: Settings) -> AsyncIterator[httpx.AsyncClient]` —
  yields a shared client, closes on exit.
- `def should_retry(exc: BaseException) -> bool` — predicate: True if
  `isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout))`
  OR `isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {429, 500, 502, 503, 504}`.
- `def retry_policy(max_attempts: int) -> tenacity.AsyncRetrying` — builds
  a tenacity `AsyncRetrying(stop=stop_after_attempt(max_attempts), wait=wait_exponential(multiplier=1, min=1, max=8), retry=retry_if_exception(should_retry), reraise=True)`.
**Usage pattern for clients (Phase 3):**
```python
async for attempt in retry_policy(settings.http_max_retries):
    with attempt:
        response = await client.get(url, params=params)
        response.raise_for_status()
```
**Constraint:** Never log the response body here — only status code, URL,
and attempt number.

### `src/museums/main.py` (SKELETON — completed in Phase 5)
**Purpose:** FastAPI app factory + lifespan.
**Contents for Phase 1:**
- `@asynccontextmanager async def lifespan(app: FastAPI) -> AsyncIterator[None]`:
  - Call `setup_logging(settings.log_level)`.
  - Create async engine, run `SELECT 1` — on failure, log and raise (uvicorn exits).
  - Yield; on shutdown dispose engine.
- `def create_app() -> FastAPI` — returns `FastAPI(title="Museums API", version="0.1.0", lifespan=lifespan)`.
- `app = create_app()`.
**Constraint:** No routers / handlers yet — Phase 5 wires those. Keep
this file ≤ 60 lines in Phase 1.

### `.env.example`
**Purpose:** Template for local dev.
**Contents:** One line per `Settings` field with a placeholder value,
including `MUSEUMS_DATABASE_URL=postgresql+asyncpg://museums:museums@db:5432/museums`.

### `alembic.ini`
**Purpose:** Alembic config.
**Contents:** Standard alembic.ini; set `sqlalchemy.url = %(MUSEUMS_DATABASE_URL)s`
with a post-interpolation in `env.py` that reads `Settings`. `script_location = alembic`.

### `alembic/env.py`
**Purpose:** Alembic environment — async mode.
**Contents:** Import `Settings` and the models `metadata`; run migrations
in async mode using `asyncio.run(run_async_migrations())` pattern.
**Constraint:** Models from Phase 2 haven't landed yet — for Phase 1 set
`target_metadata = None` and add a comment: `# TODO Phase 2: import Base.metadata`.
The subagent will wire it in Phase 2.

### `alembic/script.py.mako`
**Purpose:** Migration template.
**Contents:** Standard Alembic mako template with `upgrade()` / `downgrade()` stubs.

### `docker/Dockerfile.api`
**Purpose:** Build the FastAPI service.
**Contents:**
- Base: `python:3.13-slim`.
- Install `uv` via official installer.
- Copy `pyproject.toml` + `uv.lock`, run `uv sync --frozen`.
- Copy `src/` and `alembic/`.
- `CMD ["uv", "run", "uvicorn", "museums.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
**Constraint:** Two-stage build not required — keep it simple. Add
`HEALTHCHECK CMD curl -fsS http://localhost:8000/health || exit 1`
(stubbed; `/health` arrives in Phase 5 but compose will tolerate absence
until then).

### `docker/Dockerfile.notebook`
**Purpose:** Jupyter notebook service.
**Contents:**
- Base: `jupyter/minimal-notebook:python-3.11` (notebook image; we use
  whatever python version it ships — it calls our API, doesn't import our
  code).
- Install extra deps: `requests`, `matplotlib`, `pandas`, `numpy`.
- Working dir `/home/jovyan/work`, mount notebook/ here.
- `CMD ["start-notebook.sh", "--NotebookApp.token=''", "--NotebookApp.password=''"]`.
**Constraint:** The notebook is a demo for the grader — no auth. Acceptable
only because localhost-only.

### `docker/docker-compose.yml`
**Purpose:** Orchestrate the 3 containers.
**Services:**
- `db`: `postgres:16-alpine`; env `POSTGRES_USER=museums`,
  `POSTGRES_PASSWORD=museums`, `POSTGRES_DB=museums`; volume
  `museums_pgdata:/var/lib/postgresql/data`; healthcheck
  `pg_isready -U museums`.
- `api`: build `docker/Dockerfile.api`; depends_on `db` (condition
  `service_healthy`); `env_file: .env`; ports `8000:8000`; command runs
  `alembic upgrade head && uvicorn ...` (via an entrypoint script or
  `sh -c`).
- `notebook`: build `docker/Dockerfile.notebook`; depends_on `api`;
  ports `8888:8888`; volume `../notebook:/home/jovyan/work`;
  environment `MUSEUMS_API_URL=http://api:8000`.
**Constraint:** No named network — use the default compose network. No
restart policy — for a demo, fail-fast is better signal.

### `.pre-commit-config.yaml`
**Purpose:** Two-stage hook pipeline — fast checks on every commit,
thorough checks on push.
**Contents:**
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.0    # pin latest compatible at implementation time
    hooks:
      - id: ruff
        args: [--fix]
        exclude: ^(prototype/|notebook/)
      - id: ruff-format
        exclude: ^(prototype/|notebook/)

  - repo: local
    hooks:
      # --- pre-commit (fast) ---
      - id: pyright
        name: pyright (strict type check)
        entry: uv run pyright src/ tests/
        language: system
        types: [python]
        pass_filenames: false

      # --- pre-push (thorough) ---
      - id: pytest
        name: pytest
        entry: uv run pytest -x -q
        language: system
        types: [python]
        pass_filenames: false
        stages: [pre-push]

      - id: import-linter
        name: import-linter (layer contracts)
        entry: uv run lint-imports
        language: system
        pass_filenames: false
        stages: [pre-push]

      - id: radon-cc
        name: radon (cyclomatic complexity)
        entry: uv run radon cc src/ -a -nc
        language: system
        pass_filenames: false
        stages: [pre-push]

      - id: vulture
        name: vulture (dead code)
        entry: uv run vulture src/ --min-confidence 80
        language: system
        pass_filenames: false
        stages: [pre-push]

      # --- Custom architectural checks (pre-push) ---
      - id: check-file-length
        name: check file/function length limits
        entry: uv run python tools/pre_commit_checks/check_file_length.py
        language: system
        pass_filenames: false
        types: [python]
        stages: [pre-push]

      - id: check-datetime-patterns
        name: check datetime patterns (tz-aware)
        entry: uv run python tools/pre_commit_checks/check_datetime_patterns.py
        language: system
        pass_filenames: false
        types: [python]
        stages: [pre-push]

      - id: check-no-httpexception-outside-handlers
        name: check HTTPException only in main.py / exception_handlers
        entry: uv run python tools/pre_commit_checks/check_no_httpexception_outside_handlers.py
        language: system
        pass_filenames: false
        types: [python]
        stages: [pre-push]

      - id: check-no-sync-http-in-src
        name: check no sync HTTP (requests/urllib) in src
        entry: uv run python tools/pre_commit_checks/check_no_sync_http_in_src.py
        language: system
        pass_filenames: false
        types: [python]
        stages: [pre-push]
```
**Constraints:** Do NOT install CDDE's domain-purity, patient-data-leak,
LLM-gateway, enum-discipline, or repo-direct-instantiation checks —
they're Sanofi-specific. The import-linter contracts already cover
repo-direct-instantiation for this project.

### `tools/pre_commit_checks/_base.py`
**Purpose:** Shared AST utilities for the custom hooks.
**Classes / functions:**
- `class Violation(NamedTuple)` — `file: Path`, `line: int`, `message: str`.
- `def iter_python_files(directory: Path, exclude_patterns: list[str] | None = None) -> list[Path]` — walks, excludes `__pycache__`, `.venv`, `test`.
- `def parse_file(file_path: Path) -> ast.AST | None`.
- `def run_checker(checker_func: Callable[[Path, ast.AST], list[Violation]], files: list[Path], description: str) -> int` — prints + returns process exit code.
**Reference:** Copy verbatim from
`C:\Projects\Interviews\jobs\Sanofi-AI-ML-Lead\homework\tools\pre_commit_checks\_base.py`.
~50 lines.

### `tools/pre_commit_checks/__init__.py`
Empty (makes the folder a package so the scripts can share `_base`).

### `tools/pre_commit_checks/check_file_length.py`
**Purpose:** Enforce CLAUDE.md's file/function limits.
**Limits (calibrated for this project, stricter than CDDE):**
- `FILE_LINE_LIMIT = 200`
- `FUNCTION_LINE_LIMIT = 30`
- `CLASS_LINE_LIMIT = 150`
**Approach:** AST walk, `SizeLimitChecker(ast.NodeVisitor)` with
`visit_FunctionDef`, `visit_AsyncFunctionDef`, `visit_ClassDef`.
Exclude `__init__.py` and `alembic/versions/*.py`.
**Reference:** Adapt
`.../Sanofi-AI-ML-Lead/.../check_file_length.py` — keep the structure,
change the three limit constants, update the exclusion list.
~100 lines.

### `tools/pre_commit_checks/check_datetime_patterns.py`
**Purpose:** All audit timestamps (`created_at`, `updated_at`,
`last_refresh_at`) must be tz-aware. Catch three forbidden patterns:
- `datetime.utcnow()` — deprecated since Python 3.12.
- `datetime.now()` with no args — naive local time.
- `.replace(tzinfo=None)` — strips timezone from an audit timestamp.
**Exclude:** files matching `test_*`.
**Reference:** Copy verbatim from
`.../Sanofi-AI-ML-Lead/.../check_datetime_patterns.py` — same checker,
same constants, no adaptation needed.
~80 lines.

### `tools/pre_commit_checks/check_no_httpexception_outside_handlers.py`
**Purpose:** Enforce CLAUDE.md rule: services, workflows, routers, and
repositories raise domain exceptions, never `HTTPException`. The only
file allowed to import / raise `HTTPException` is `main.py` (global
handlers) or a future `exception_handlers.py`.
**Approach:**
- AST walk `src/museums/` looking for:
  - `from fastapi import HTTPException` or `from fastapi.exceptions import HTTPException` or `fastapi.HTTPException`.
  - `raise HTTPException(...)` calls.
- Allowlist: files whose path ends in `main.py` or `exception_handlers.py`.
- Emit violation: `"{file}:{line}: HTTPException is only allowed in main.py / exception_handlers.py — raise a domain exception instead"`.
**Reference:** No CDDE equivalent — net-new for this project. Shape
matches `check_datetime_patterns.py`.
~70 lines.

### `tools/pre_commit_checks/check_no_sync_http_in_src.py`
**Purpose:** Enforce CLAUDE.md: all external HTTP calls in `src/` go
through `httpx` async. Catch `import requests`, `import urllib`,
`import urllib3`, `import http.client` in any `src/**/*.py` file.
**Approach:** AST walk, check `ast.Import` and `ast.ImportFrom` nodes.
**Excluded paths:** `notebook/` (server-side `requests` is allowed
there — different runtime); `tests/` (no blanket ban, though preferred).
**Reference:** No CDDE equivalent — net-new. ~50 lines.

### `README.md`
**Purpose:** Minimal run instructions.
**Contents:**
- One-paragraph overview.
- **Quickstart** section: `cp .env.example .env && docker compose up --build`.
- **Endpoints** section with `/health`, `/refresh`, `/museums`,
  `/cities/populations`, `/harmonized`, `/regression`.
- **Notebook** section: `open http://localhost:8888`.
- **Dev loop** section: `uv sync`, `uv run pre-commit install --install-hooks`, `uv run pytest`, `uv run alembic upgrade head`.
**Constraint:** No architecture diagrams yet — those go in
`ARCHITECTURE.md` (Phase 6).

## Test files to create

### `tests/__init__.py`
Empty.

### `tests/conftest.py`
**Purpose:** Shared fixtures (expanded across phases).
**Contents for Phase 1:**
- `settings` fixture: returns `Settings` with test overrides (SQLite-memory
  URL is NOT used — we use a dedicated `museums_test` Postgres DB via env).
  For Phase 1, just return default-overridden `Settings` for config tests.
- `anyio_backend` fixture returning `"asyncio"`.

### `tests/test_config.py`
**Tests to write (4):**
- `test_settings_loads_defaults_from_env_prefix` — set env vars, build
  `Settings()`, assert values.
- `test_settings_rejects_invalid_cooldown_hours` — `refresh_cooldown_hours=0`
  raises `ValidationError`.
- `test_settings_rejects_invalid_log_level` — `log_level="TRACE"` raises.
- `test_get_settings_is_memoized` — two calls return same instance.

### `tests/test_exceptions.py`
**Tests to write (3):**
- `test_refresh_cooldown_error_exposes_retry_after_seconds` — construct
  with 3600, assert `exc.retry_after_seconds == 3600`.
- `test_not_found_error_includes_entity_and_identifier_in_message` —
  `str(exc)` contains both.
- `test_external_service_error_stores_service_name` — each subclass has
  expected `service_name`.

### `tests/test_http_client.py`
**Tests to write (4):**
- `test_should_retry_returns_true_for_5xx` — build fake
  `httpx.HTTPStatusError` with 503, assert `should_retry(exc) is True`.
- `test_should_retry_returns_false_for_4xx` — 404, assert False.
- `test_should_retry_returns_true_for_connect_error` — assert True.
- `test_retry_policy_stops_after_max_attempts` — use `respx` to make
  a 503-always endpoint, assert tenacity gives up after 3 attempts and
  re-raises.
**Fixtures:** `respx_mock` from `respx.mock()`.

## Phase 1 tooling gate (must pass before reporting complete)

```bash
uv sync
uv run pre-commit install --install-hooks   # installs both commit + push hooks
uv run pre-commit run --all-files            # full ruff + pyright pass
uv run pre-commit run --hook-stage pre-push --all-files  # pytest + import-linter + custom checks
docker compose config                        # validates compose YAML
```

Expected: all green, 11 tests pass (4 config + 3 exceptions + 4 http_client).
The custom pre-push checks (`check_file_length`, `check_datetime_patterns`,
`check_no_httpexception_outside_handlers`, `check_no_sync_http_in_src`)
must print `OK:` lines — they operate on `src/` which is small in Phase 1
but must already be clean.

## Out of scope for Phase 1

- No database models or migrations (Phase 2).
- No external API clients (Phase 3).
- No routers, no /health endpoint yet (Phase 5).
- No notebook (Phase 6).
- `alembic/env.py` references no models — deferred to Phase 2.
