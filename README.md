# Museums vs. City Population

![CI](https://github.com/matt-grain/museum-analysis/actions/workflows/ci.yml/badge.svg)

Source: [github.com/matt-grain/museum-analysis](https://github.com/matt-grain/museum-analysis)

A FastAPI service that correlates museum visitor counts with city populations
using data sourced from Wikipedia and Wikidata, then fits a log-log linear
regression to quantify the relationship.

## Quickstart

```bash
cp .env.example .env
wsl docker compose -f docker/docker-compose.yml up --build
```

The API will be available at `http://localhost:8000` and the Jupyter notebook
at `http://localhost:8888`.

> **Windows note:** Docker Desktop on Windows requires all `docker` and
> `docker compose` commands to be run through WSL (`wsl docker compose ...`).
> Running them from Git Bash directly will fail because the Windows socket is
> not shared.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/refresh` | Fetch fresh data from Wikipedia/Wikidata (cooldown: 24h) |
| GET | `/museums` | List ingested museums (paginated) |
| GET | `/cities/populations` | List city population time series |
| GET | `/harmonized` | Harmonized museum-visitor/city-population pairs |
| GET | `/regression` | Fit result: coefficient, intercept, R², scatter data |

Pass `?force=true` to `/refresh` to bypass the cooldown.

## Notebook

1. Start all containers: `wsl docker compose -f docker/docker-compose.yml up --build`
2. Open `http://localhost:8888` in your browser.
3. Open `regression_analysis.ipynb` and run **Run All**.
4. Cell 1 triggers the data refresh — first run takes 30–120 s. Subsequent runs
   within 24 h will print the expected cooldown message and continue.

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full layer breakdown, data flow
diagrams, and real code extracts.

## Design Rationale

See [`docs/PROJECT.md`](docs/PROJECT.md) for why we chose dual-source ingestion,
per-city OLS interpolation, log-log regression, and PostgreSQL over SQLite.

## Decisions

See [`decisions.md`](decisions.md) for all Architecture Decision Records (ADRs),
including the dual-source Wikipedia/Wikidata strategy, refresh cooldown design,
and the documented service-to-service dependency between `RegressionService` and
`HarmonizationService`.

## Dev Loop

```bash
uv sync
uv run pre-commit install --install-hooks
uv run pytest
wsl docker compose -f docker/docker-compose.yml up -d db
uv run alembic upgrade head
```

Run the full pre-push gate manually:

```bash
uv run pre-commit run --all-files
uv run pre-commit run --hook-stage pre-push --all-files
```

## Troubleshooting

**Database not responding / containers not starting**

```bash
wsl docker compose -f docker/docker-compose.yml logs db
```

Check that the `db` service reached `healthy` status. If not, try
`wsl docker compose -f docker/docker-compose.yml down -v` to wipe the volume,
then `up --build` again.

**Wikidata returns 429 (Too Many Requests)**

Wait 10 minutes, then re-trigger with the force flag:

```bash
curl -X POST "http://localhost:8000/refresh?force=true"
```

The 24h cooldown exists specifically to avoid hammering Wikidata. If you need
fresh data within the cooldown window, `?force=true` bypasses it.

**`/regression` returns 422 (Insufficient Data)**

The regression requires at least 5 harmonized rows. Check `/harmonized` —
if it returns an empty array or fewer than 5 rows, the harmonization step
dropped most museums (likely because population data was sparse or the
refresh failed partway through). Re-run `/refresh?force=true` and check
the API logs for `museum_skipped_no_population_fit` warnings.
