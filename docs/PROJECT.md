# Museum Visitors vs. City Population — Project Design

## Goal

Build a small, harmonized dataset of high-traffic museums (>2M visitors/year) and
the populations of the cities they sit in, then fit a linear regression
correlating museum attendance with city population. Deliver it as a
docker-composed, FastAPI-packaged service with a companion Jupyter notebook
that presents the regression results visually.

## Shape of the solution

Three containers, one compose file.

```
┌──────────────┐      ┌──────────────┐      ┌────────────────┐
│  PostgreSQL  │◀─────│   FastAPI    │◀─────│    Jupyter     │
│              │      │  (src/…)     │ HTTP │  (notebook.    │
│  raw tables  │      │              │      │   ipynb)       │
│  + harmonized│      │  /refresh    │      │                │
│    view      │      │  /museums    │      │  calls API,    │
│              │      │  /cities/…   │      │  visualizes    │
│              │      │  /harmonized │      │                │
│              │      │  /regression │      │                │
└──────────────┘      └──────────────┘      └────────────────┘
```

The notebook never touches the database directly — it calls the API, which
keeps the layering honest and lets a future public front-end reuse the same
contract.

## Data sources

- **Museums** — Wikipedia MediaWiki Action API to fetch the canonical page
  `List_of_most_visited_museums` and extract the museum names from its table.
  Then enrich each via the Wikidata Query Service (SPARQL) to obtain the
  QID, city, country, and all per-year visitor records (property P1174 with
  P585 qualifier).
- **City populations** — Wikidata Query Service (SPARQL) for historical
  population time series (property P1082 with P585 qualifier).

**Why both Wikipedia and Wikidata?** The brief says "use the Wikipedia APIs"
but the actual list page is a rendered HTML table — not a stable structured
source. Wikidata is the structured backbone of Wikipedia and exposes exactly
the fields we need. Using the MediaWiki API for the canonical list and
Wikidata for the characteristics answers the letter of the prompt *and* gives
us a defensible, scriptable pipeline.

## Harmonization — the hard part

The two sources don't align on time:

- A museum may have several yearly visitor records (e.g., Louvre 2019, 2022, 2023).
- A city may have population records on arbitrary years (census years, UN
  estimates, etc.).

For each museum record we want a **visitors ↔ population** pair at the
**same year**. Approach:

1. For each city, fit a tiny per-city `population ~ year` OLS model on the
   available data points. This gives a continuous estimator for any year.
2. For each museum, pick the visitor record **nearest to today** (most
   recent wins — that's the most policy-relevant data point).
3. Project the city's population at that visitor-year using the per-city
   fit from step 1.
4. Produce one `(museum, city, year, visitors, population_est)` row per
   museum — that's the harmonized dataset.

This logic lives in the service layer (`services/harmonization_service.py`),
not in the notebook.

## Regression

- `log(visitors) ~ log(population_est)` — both variables are heavy-tailed
  (a handful of megacities and blockbuster museums dominate). Log-log turns
  the relationship into an interpretable elasticity and stops Louvre from
  owning the fit.
- Single-feature OLS via scikit-learn or statsmodels. The point is
  correlation, not prediction accuracy.
- Report: coefficient, intercept, R², and predicted-vs-actual scatter.

## Refresh policy

- `/refresh` is an **explicit POST** — user-triggered, not on startup.
- Rate-limit guard: the endpoint reads a `last_refresh_at` timestamp from
  the DB and refuses to re-fetch if it's younger than N hours (default 24).
  Wikidata SPARQL is notoriously flaky and rate-limited, so we don't want
  to hammer it on every container restart.
- Pass `?force=true` to override.

## Database choice — PostgreSQL

The dataset is small (~70 museums, ~70 cities) — SQLite would be adequate
for the MVP. We pick Postgres anyway because:

- The brief asks for an MVP that **could later scale** to a public audience.
  Swapping SQLite → Postgres post-hoc is not free; starting on Postgres is.
- Docker Compose makes running Postgres free in dev.
- SQLAlchemy 2.0 async + Alembic is the same code regardless.

## Rejected alternatives

| Choice | Rejected | Why |
|---|---|---|
| HTML-scrape the Wikipedia page | ❌ | Fragile to layout changes; Wikidata gives the same data, structured. |
| GeoNames / SimpleMaps for city population | ❌ | Metro-area vs. administrative-city mismatch is painful for megacities (Tokyo, Paris). Wikidata uses the same administrative entity the museum is linked to — symmetric. |
| Per-city-year exact matching, drop unmatched | ❌ | Would lose ~40% of museums. The per-city OLS fit is a defensible interpolation. |
| Notebook reads the DB directly | ❌ | Breaks the layer boundary; makes the API a demo-only decoration. |
| Latest-visitor-year defaults | ❌ | "Latest" means "nearest to today among available" — explicit, not implicit. |
| SQLite | ❌ | Velocity gain doesn't survive the "could later scale" question. |

## Tech stack

- **Python 3.13**, `uv` for package management.
- **FastAPI** (async), **Pydantic v2**, **SQLAlchemy 2.0 async**, **Alembic**.
- **PostgreSQL 16** via docker-compose.
- **httpx** async for MediaWiki and Wikidata calls.
- **scikit-learn** for the regression (linear_model.LinearRegression).
- **Jupyter** in its own container (`jupyter/base-notebook` + installed deps).
- **pytest + pytest-asyncio** for tests; **pyright strict**, **ruff**,
  **import-linter** for the architectural gate.
- Keep it ~50 tests, one `src/museums/` package, no FSMs (no stateful
  entities in this domain).

## What this project is not

- Not a production-grade ETL — one-shot refresh, no incremental sync.
- Not a model-serving platform — the regression is a demo, not a product.
- Not authenticated — public demo endpoints.
- Not a full observability stack — structured logs, no tracing, no metrics.

The design is scoped to "rapid prototype + defensible MVP," per the brief.
