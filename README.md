# Museums vs. City Population

A FastAPI service that correlates museum visitor counts with city populations
using data sourced from Wikipedia and Wikidata, then fits a log-log linear
regression to quantify the relationship.

## Quickstart

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

The API will be available at `http://localhost:8000` and the Jupyter notebook
at `http://localhost:8888`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/refresh` | Fetch fresh data from Wikipedia/Wikidata (cooldown: 24h) |
| GET | `/museums` | List ingested museums |
| GET | `/cities/populations` | List city population time series |
| GET | `/harmonized` | Harmonized museum-visitor/city-population pairs |
| GET | `/regression` | Fit result: coefficient, intercept, R², scatter data |

Pass `?force=true` to `/refresh` to bypass the cooldown.

## Notebook

Open `http://localhost:8888` — the notebook at `notebook/regression_analysis.ipynb`
calls the API and renders the regression scatter plot.

## Dev loop

```bash
uv sync
uv run pre-commit install --install-hooks
uv run pytest
uv run alembic upgrade head  # requires a running Postgres instance
```

Run the full pre-push gate manually:

```bash
uv run pre-commit run --hook-stage pre-push --all-files
```
