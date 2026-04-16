# Phase 6 — Notebook, CI & Docs

**Agent:** `python-fastapi`
**Depends on:** Phase 5 (full API surface running).
**Produces:** Final deliverables — Jupyter notebook (the grader-facing
artifact), GitHub Actions CI, `ARCHITECTURE.md`, `decisions.md`,
finalized `README.md`.

The notebook is the **only** consumer that matters for the grader demo.
It tells the story end-to-end. CI is the bare-minimum signal to the
grader that the project is wired up for continuous verification.

**Remote:** `https://github.com/matt-grain/museum-analysis`.

## Notebook narrative (3 acts, one section each)

### Files to create (new)

### `notebook/regression_analysis.ipynb`
**Runtime env:** Runs in the `notebook` docker container; calls the `api`
container at `http://api:8000`.

**Cell 0 — Setup:**
```python
import os, requests, pandas as pd, numpy as np, matplotlib.pyplot as plt
API = os.environ.get("MUSEUMS_API_URL", "http://api:8000")

def api_get(path, **params):
    r = requests.get(f"{API}{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()

def api_post(path, **params):
    r = requests.post(f"{API}{path}", params=params, timeout=600)
    r.raise_for_status()
    return r.json()
```

**Cell 1 — Refresh data (manual trigger):**
Markdown cell explaining: "Refresh is explicit. First call populates the
DB from Wikipedia + Wikidata. Re-running within 24h is blocked unless
`force=true`."
Code cell: `try: print(api_post("/refresh")) except Exception as e: print("already refreshed or failed:", e)`.

**Act 1 — Raw data**
- Markdown: "We fetch two raw views: museums with their visitor-year
  records, and cities with their full population history."
- `museums = pd.json_normalize(api_get("/museums", limit=200)["items"])` — flatten.
- Show head + row count.
- `cities = api_get("/cities/populations")` (list); flatten population series into a long-format DataFrame.
- Plot population time series for top 10 cities by latest population.
- Comment visible: "These two views don't align on year. We need harmonization."

**Act 2 — Harmonization**
- Markdown: "Per-city OLS fit lets us estimate population at any year.
  For each museum we take its most-recent visitor record and look up
  the city's estimated population at that year."
- `harmonized = pd.DataFrame(api_get("/harmonized"))`.
- Show head + row count, note how many museums survived (log drops counted via raw museum count - harmonized count).
- Plot per-city population: scatter raw population_records + overlay
  the extrapolated fit line + mark the museum-year with its estimated
  population. Do this for 3-6 example cities (Paris, London, Tokyo, NYC, etc.).
- Highlight extrapolated vs. interpolated rows (`population_is_extrapolated`) using different markers.

**Act 3 — Regression**
- Markdown: "Log-log OLS. Elasticity coefficient tells us how museum
  attendance scales with city size."
- `reg = api_get("/regression")`.
- Print `coefficient`, `intercept`, `r_squared`, `n_samples`.
- Scatter plot: x = `log_population_est`, y = `log_visitors`, overlay
  fit line. Highlight residual outliers (top/bottom 5 by `|residual|`).
- Predicted-vs-actual plot: `log_visitors` on x, `predicted_log_visitors`
  on y, plus y=x reference line.
- Markdown interpretation: "Elasticity ≈ {coefficient:.2f} suggests
  museum visits scale sublinearly with city population — a doubling in
  city size produces only a ~{2**coefficient - 1:.0%} increase in
  visitors. This is the expected pattern when tourism draws from beyond
  the host city."

**Notebook hygiene:**
- All outputs cleared before commit (run `nbstripout` or clear manually).
- No hardcoded API keys, no localhost-only assumptions (use `MUSEUMS_API_URL`).
- ≤ 25 cells total.

### `.github/workflows/ci.yml`
**Purpose:** Bare-minimum GitHub Actions CI so reviewers see a green
signal on the default branch. Runs the tooling gate + pytest against a
real Postgres service container.
**Trigger:** `on: { push: { branches: [main] }, pull_request: { branches: [main] } }`.
**Jobs:**
- **`checks`** (single job, single matrix entry):
  - `runs-on: ubuntu-latest`.
  - **Services:** `postgres: { image: postgres:16-alpine, env: { POSTGRES_USER: museums, POSTGRES_PASSWORD: museums, POSTGRES_DB: museums_test }, ports: ['5432:5432'], options: "--health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 5" }`.
  - **Steps:**
    1. `actions/checkout@v4`.
    2. `astral-sh/setup-uv@v3` with `version: latest`.
    3. `uv python install 3.13`.
    4. `uv sync --frozen`.
    5. `uv run pre-commit run --all-files` — runs ruff + pyright on
       every file (fast checks from Phase 1's pre-commit config).
    6. `uv run alembic upgrade head` with
       `env: MUSEUMS_DATABASE_URL: postgresql+asyncpg://museums:museums@localhost:5432/museums_test`.
    7. `uv run pre-commit run --hook-stage pre-push --all-files` with the
       same env — runs pytest, import-linter, radon, vulture, and the 4
       custom architectural checks.
**Constraints:**
- No matrix (Python 3.13 only). No Docker build step (covered manually
  via the README quickstart). No deployment.
- Job total wall-clock target: ≤ 5 minutes on ubuntu-latest. If it
  grows past that, split tooling-gate and pytest into separate jobs.
- **No secrets used** — DB credentials are inline because this is a
  throwaway container.
- Fail-fast — all steps are required; no `continue-on-error`.
**Reference:** No in-repo reference (new file). Standard GH Actions YAML.

### `.github/dependabot.yml` (optional, minimal)
**Purpose:** Keep `uv.lock` and GH Action versions fresh.
**Contents:**
```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "monthly" }
```
Skip `pip` ecosystem (uv-managed deps — dependabot doesn't speak uv
natively yet). Purely a "grader-nice-to-have" — if time pressed, skip.

### `ARCHITECTURE.md`
**Purpose:** Document the shipped structure.
**Required sections** (per `~/.claude/rules/shared/documentation.md`):
1. **Overview** — one paragraph: museum/city harmonization + log-log regression served via FastAPI, notebook-facing.
2. **Tech Stack** — bullet list (Python 3.13, FastAPI, SQLAlchemy 2.0 async, Postgres 16, httpx, tenacity, sklearn, Jupyter).
3. **Project Structure** — tree view of `src/museums/` with one-line descriptions per module.
4. **Layer Responsibilities** — routers / services / repositories / clients / models / schemas; what each does and must not do. Include a short real extract from `services/harmonization_service.py` as the canonical pattern example.
5. **Data Flow** — walk through a `POST /refresh` request: route → IngestionService → MediaWiki + Wikidata clients → repositories → DB; then a `GET /regression` request: route → RegressionService → HarmonizationService → repositories → compute → response.
6. **Key Domain Concepts** — Museum, City, VisitorRecord, PopulationRecord, RefreshState. Plus the derived `HarmonizedRow` and `RegressionResult`.
7. **State Machines** — "None — no stateful entities in this domain."
**Constraint:** ≤ 250 lines. Link `docs/PROJECT.md` as "design rationale."

### `decisions.md`
**Purpose:** Architecture Decision Records for non-obvious choices.
**Entries to include (one per non-trivial decision, follow ADR format from `~/.claude/rules/shared/documentation.md`):**

1. **2026-04-16 — Wikipedia MediaWiki Action API + Wikidata SPARQL (dual source)**
   - Context: Brief says "use Wikipedia APIs"; canonical list is an HTML page.
   - Decision: Use MediaWiki Action API for the canonical museum list, Wikidata SPARQL for structured enrichment.
   - Alternatives: HTML scrape; Wikidata-only with a pre-filter on visitors > 2M.
   - Consequences: Two API surfaces to maintain; stronger story for grader.

2. **2026-04-16 — PostgreSQL over SQLite**
   - Context: Small dataset (~70 museums). SQLite is viable for MVP.
   - Decision: Postgres 16 via docker-compose.
   - Alternatives: SQLite; DuckDB.
   - Consequences: +1 container; docker-compose has always-on DB; "could later scale" story holds.

3. **2026-04-16 — Per-city OLS linear fit for year-level population interpolation**
   - Context: Wikidata populations are sparse; museum visitor years don't align with population years.
   - Decision: Fit `population ~ year` per city on all available points (≥ 2); extrapolate at museum year. Single-point cities use a ±2y tolerance fallback.
   - Alternatives: Nearest-neighbor year match (drops ~40% of museums); nationwide growth-rate extrapolation.
   - Consequences: Extrapolation risk flagged via `population_is_extrapolated` field; surfaced in notebook viz.

4. **2026-04-16 — Log-log linear regression (not raw linear)**
   - Context: Both variables heavy-tailed (Louvre, Tokyo).
   - Decision: `log(visitors) ~ log(population)`.
   - Alternatives: Raw linear; Poisson regression.
   - Consequences: Interpretable as elasticity; mitigates Louvre dominating the fit.

5. **2026-04-16 — Explicit refresh with 24h cooldown**
   - Context: Wikidata SPARQL is rate-limited and flaky.
   - Decision: `POST /refresh` is user-triggered; guarded by 24h cooldown; `?force=true` override.
   - Alternatives: Cron refresh; refresh-on-startup.
   - Consequences: First container start requires manual `/refresh` call (notebook handles this in Cell 1).

6. **2026-04-16 — Notebook calls API, never DB**
   - Context: Brief says notebook should "programmatically use your other code."
   - Decision: Notebook uses `requests` to hit the FastAPI endpoints; no DB connection.
   - Alternatives: Notebook imports services directly; notebook reads Postgres.
   - Consequences: Keeps layer boundaries honest; demo-able end-to-end.

7. **2026-04-16 — IngestionWorkflow is a workflow, not a service**
   - Context: CLAUDE.md forbids services from holding `AsyncSession`.
     Ingestion needs a transaction boundary across five repositories.
   - Decision: Place the ingestion orchestrator under `workflows/`. The
     workflow layer is the one allowed to own the session and call
     `commit()` / `rollback()`.
   - Alternatives: Keep it as a service with a documented exception;
     introduce a full Unit-of-Work abstraction.
   - Consequences: +1 layer in the project structure; cleaner
     import-linter contracts; aligns with the python-fastapi rules.

8. **2026-04-16 — `RegressionService` depends on `HarmonizationService`**
   - Context: The python-fastapi guideline prefers services to depend on
     repositories only. Regression is a compute pipeline step that
     follows harmonization.
   - Decision: `RegressionService` composes `HarmonizationService` for
     input. Rationale: the two steps form a single pipeline; re-deriving
     harmonization from repos inside `RegressionService` would duplicate
     logic.
   - Alternatives: Have the router call both services sequentially and
     pass harmonization output into regression; introduce a
     `RegressionWorkflow` that glues them.
   - Consequences: One documented service-to-service edge. Easy to
     split later if regression grows additional inputs.

### `README.md` (FINALIZE — extend Phase 1 version)
**Add:**
- **CI badge** at the top: `![CI](https://github.com/matt-grain/museum-analysis/actions/workflows/ci.yml/badge.svg)`.
- **Repo link** one-liner under the title.
- **Architecture section** — link to `ARCHITECTURE.md`.
- **Design rationale** — link to `docs/PROJECT.md`.
- **Decisions** — link to `decisions.md`.
- **Notebook usage** — "Open http://localhost:8888, run all cells. Cell 1
  triggers the data refresh (first run takes 30-60s)."
- **Troubleshooting** — 3 common failures:
  - DB not up: `docker compose logs db`.
  - Wikidata 429: wait 10 min, re-run `/refresh?force=true`.
  - Empty `/regression`: check `/harmonized` for `InsufficientDataError` cause.

## Files to modify

### `docs/PROJECT.md` (MINOR — optional)
If any design choice drifted during implementation (e.g., we ended up
using Action API `wikitext` instead of rendered HTML and that wasn't in
the spec), append a brief "Implementation notes" section at the bottom.

## Test files

No new tests in Phase 6 — the notebook is manually validated. However:

### Manual QA checklist (subagent must verify before reporting complete):
1. `docker compose up --build` succeeds and all 3 services reach `healthy`.
2. `curl http://localhost:8000/health` returns 200.
3. `curl -X POST http://localhost:8000/refresh` returns 202 within 120s
   (first run) or 429 (within cooldown).
4. `curl http://localhost:8000/museums | jq '.pagination.total'` > 50.
5. `curl http://localhost:8000/harmonized | jq 'length'` > 20.
6. `curl http://localhost:8000/regression | jq '.r_squared'` > 0.1 (sanity).
7. Notebook opens at `http://localhost:8888`; "Run All" completes without
   error; plots render.

## Phase 6 tooling gate

```bash
uv run ruff check .
uv run pytest -v                       # cumulative ~53 tests still green
docker compose up --build              # manual verification
jupyter nbconvert --to notebook --execute notebook/regression_analysis.ipynb \
    --output /tmp/executed.ipynb       # programmatic check the notebook runs
```

## Acceptance

Phase 6 is complete when:
- Notebook executes top-to-bottom against `docker compose up` without errors.
- All three MD docs exist and are consistent with the code.
- Cumulative test count: ~58 (no regression from Phase 5).
- `docker compose config` validates.
- GitHub Actions CI run is green on the feature branch pushed to
  `matt-grain/museum-analysis`.
- No `TODO` / `FIXME` without tracker refs remain anywhere.

## Out of scope for Phase 6

- No new endpoints.
- No new services.
- No Docker-image CI build step (too slow for take-home).
- No deployment workflow.
