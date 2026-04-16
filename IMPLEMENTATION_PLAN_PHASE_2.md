# Phase 2 — Data Layer

**Agent:** `python-fastapi`
**Depends on:** Phase 1 (config, exceptions, Alembic scaffold).
**Produces for later phases:** ORM models, repositories, initial migration,
test factories. Phase 3 uses models + repositories for ingestion; Phase 4
uses them for harmonization; Phase 5 wires them via `Depends()`.

Read `CLAUDE.md` and `docs/PROJECT.md` before starting.

## Data model (ER sketch)

```
Museum (1) ────< (N) VisitorRecord
  │
  └─ city_id ──▶ City (1) ────< (N) PopulationRecord

RefreshState (singleton row)
```

- **Museum**: one row per Wikipedia-listed museum.
- **VisitorRecord**: one row per (museum, year) visitor count from Wikidata.
- **City**: one row per unique city referenced by a museum.
- **PopulationRecord**: one row per (city, year) population datapoint.
- **RefreshState**: one row (id=1) tracking `last_refresh_at`.

## Files to create (new)

### `src/museums/models/__init__.py`
**Purpose:** Re-export all model classes and `Base` for Alembic autogenerate.
**Contents:**
```python
from .base import Base, TimestampMixin
from .city import City
from .museum import Museum
from .population_record import PopulationRecord
from .refresh_state import RefreshState
from .visitor_record import VisitorRecord

__all__ = ["Base", "TimestampMixin", "City", "Museum",
           "PopulationRecord", "RefreshState", "VisitorRecord"]
```

### `src/museums/models/base.py`
**Purpose:** Declarative base + mixins.
**Classes:**
- `class Base(AsyncAttrs, DeclarativeBase)` — SQLAlchemy 2.0 async base.
- `class TimestampMixin`:
  - `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)`
  - `updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)`
**Constraint:** Never store naive datetimes — always `timezone=True`.

### `src/museums/models/city.py`
**Purpose:** City ORM model.
**Class:** `City(Base, TimestampMixin)`; `__tablename__ = "cities"`.
**Fields:**
- `id: Mapped[int] = mapped_column(primary_key=True)`
- `wikidata_qid: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)` — e.g. `Q90`.
- `name: Mapped[str] = mapped_column(String(200), nullable=False)`
- `country: Mapped[str | None] = mapped_column(String(200))`
- `population_records: Mapped[list[PopulationRecord]] = relationship(back_populates="city", cascade="all, delete-orphan")`
- `museums: Mapped[list[Museum]] = relationship(back_populates="city")`
**Constraint:** QID is the natural key across refreshes — upsert on QID.

### `src/museums/models/museum.py`
**Purpose:** Museum ORM model.
**Class:** `Museum(Base, TimestampMixin)`; `__tablename__ = "museums"`.
**Fields:**
- `id: Mapped[int] = mapped_column(primary_key=True)`
- `wikidata_qid: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)` — nullable because MediaWiki may find a museum the SPARQL join misses.
- `name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)`
- `wikipedia_title: Mapped[str] = mapped_column(String(300), nullable=False)` — title from the Wikipedia list page.
- `city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id", ondelete="SET NULL"), index=True)`
- `country: Mapped[str | None] = mapped_column(String(200))`
- `city: Mapped[City | None] = relationship(back_populates="museums")`
- `visitor_records: Mapped[list[VisitorRecord]] = relationship(back_populates="museum", cascade="all, delete-orphan")`
**Constraint:** `name` is unique — the Wikipedia list page is the canonical
identifier. Upsert on name.

### `src/museums/models/visitor_record.py`
**Purpose:** Per-year visitor count for a museum.
**Class:** `VisitorRecord(Base, TimestampMixin)`; `__tablename__ = "visitor_records"`.
**Fields:**
- `id: Mapped[int] = mapped_column(primary_key=True)`
- `museum_id: Mapped[int] = mapped_column(ForeignKey("museums.id", ondelete="CASCADE"), index=True, nullable=False)`
- `year: Mapped[int] = mapped_column(Integer, nullable=False)` — 2000..2100.
- `visitors: Mapped[int] = mapped_column(BigInteger, nullable=False)`
- `museum: Mapped[Museum] = relationship(back_populates="visitor_records")`
- `__table_args__ = (UniqueConstraint("museum_id", "year", name="uq_visitor_records_museum_year"), CheckConstraint("year >= 2000 AND year <= 2100"), CheckConstraint("visitors > 0"))`.

### `src/museums/models/population_record.py`
**Purpose:** Per-year population datapoint for a city.
**Class:** `PopulationRecord(Base, TimestampMixin)`.
**Fields:** Mirror of `VisitorRecord`:
- `id, city_id (FK CASCADE), year (2000..2100), population (BigInteger > 0)`.
- Unique `(city_id, year)`.
- Relationship `city` with `back_populates="population_records"`.

### `src/museums/models/refresh_state.py`
**Purpose:** Singleton tracking last refresh.
**Class:** `RefreshState(Base)` (no TimestampMixin — only `last_refresh_at` matters).
**Fields:**
- `id: Mapped[int] = mapped_column(primary_key=True)` — always 1 (enforced by CheckConstraint).
- `last_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))`
- `last_refresh_museums_count: Mapped[int | None]`
- `last_refresh_cities_count: Mapped[int | None]`
- `__table_args__ = (CheckConstraint("id = 1", name="ck_refresh_state_singleton"),)`.

### `src/museums/repositories/__init__.py`
Re-export all repositories for ergonomic imports.

### `src/museums/repositories/city_repository.py`
**Purpose:** City CRUD + upsert.
**Class:** `CityRepository`; constructor `__init__(self, session: AsyncSession)`.
**Methods:**
- `async def get_by_qid(self, qid: str) -> City | None`
- `async def list_all(self) -> list[City]` — orders by name.
- `async def upsert_by_qid(self, qid: str, name: str, country: str | None) -> City` — returns newly created OR updated row. Use
  `insert(City).values(...).on_conflict_do_update(index_elements=["wikidata_qid"], set_={...}).returning(City)` via `session.execute`.
**Constraint:** Only this layer builds queries. Never call `session.commit()`
here — services control transactions.

### `src/museums/repositories/museum_repository.py`
**Purpose:** Museum CRUD + upsert + paginated list.
**Class:** `MuseumRepository`.
**Methods:**
- `async def get_by_name(self, name: str) -> Museum | None`
- `async def list_paginated(self, skip: int, limit: int) -> tuple[list[Museum], int]` — returns `(items, total)`; joinedload on `city` and `visitor_records`.
- `async def upsert_by_name(self, name: str, wikipedia_title: str, wikidata_qid: str | None, city_id: int | None, country: str | None) -> Museum` — `on_conflict_do_update` on `name`.
- `async def delete_all(self) -> None` — used at refresh start in Phase 3
  if we go with full-wipe (not recommended) — included for completeness
  but Phase 3 will prefer upsert.

### `src/museums/repositories/visitor_record_repository.py`
**Purpose:** Bulk insert + query visitor records.
**Class:** `VisitorRecordRepository`.
**Methods:**
- `async def upsert_many(self, museum_id: int, records: Iterable[tuple[int, int]]) -> int` — `records` is `[(year, visitors), ...]`; returns count inserted/updated via `on_conflict_do_update` on `(museum_id, year)`.
- `async def list_for_museum(self, museum_id: int) -> list[VisitorRecord]` — ordered by year desc.

### `src/museums/repositories/population_record_repository.py`
**Purpose:** Bulk insert + per-city query.
**Class:** `PopulationRecordRepository`.
**Methods:**
- `async def upsert_many(self, city_id: int, records: Iterable[tuple[int, int]]) -> int` — on_conflict on `(city_id, year)`.
- `async def list_for_city(self, city_id: int) -> list[PopulationRecord]` — ordered by year asc.
- `async def list_all_grouped(self) -> dict[int, list[PopulationRecord]]` — `{city_id: [records sorted by year]}`; used by harmonization service.

### `src/museums/repositories/refresh_state_repository.py`
**Purpose:** Read/write the singleton.
**Class:** `RefreshStateRepository`.
**Methods:**
- `async def get(self) -> RefreshState` — SELECT WHERE id=1; if missing, INSERT then return.
- `async def mark_refreshed(self, museums: int, cities: int) -> RefreshState` — UPDATE sets `last_refresh_at = now()`, counts.
**Constraint:** `get()` must auto-create the row on first call — the app
should work on a fresh DB without a seed migration for this row.

## Migration

### `alembic/versions/0001_initial.py`
**Purpose:** Create all 5 tables with indexes, unique constraints, check
constraints, and FKs exactly matching the models.
**Generation:** Use `uv run alembic revision --autogenerate -m "initial schema"`
AFTER models are imported in `alembic/env.py`. Review the generated file
and:
- Verify FK `ondelete` settings.
- Verify all `CheckConstraint` entries are present (SQLAlchemy sometimes
  drops them — add manually if missing).
- Verify indexes on FK columns.
- Remove any autogenerated diffs from Alembic's internal tables.
**After generation:** `uv run alembic upgrade head` against the local
postgres container and inspect schema with `psql -c "\d+ museums"` to
verify.
**Also update `alembic/env.py`:** replace the `target_metadata = None`
stub from Phase 1 with `from museums.models import Base; target_metadata = Base.metadata`.

## Test files

### `tests/conftest.py` (MODIFY — extend Phase 1 version)
**Add:**
- `async_engine` session-scoped fixture: creates async engine pointing at
  `museums_test` DB; runs `Base.metadata.drop_all` + `create_all` once at
  session start.
- `db_session` function-scoped fixture: yields an `AsyncSession` wrapped in
  an outer transaction that rolls back at teardown (so tests never leak).
- Import factories from `tests/factories.py` and expose as fixtures
  (`city_factory`, `museum_factory`, etc.).
**Constraint:** Tests MUST use a real Postgres (via docker-compose or
local) — no SQLite substitution. Rationale: async drivers + JSON types +
`on_conflict_do_update` behave differently.

### `tests/factories.py`
**Purpose:** Data builders for tests.
**Functions (all async):**
- `async def build_city(session: AsyncSession, *, qid: str = "Q90", name: str = "Paris", country: str = "France") -> City`
- `async def build_museum(session: AsyncSession, *, name: str = "Louvre", wikipedia_title: str = "Louvre", city: City | None = None, qid: str | None = "Q19675") -> Museum`
- `async def build_visitor_record(session: AsyncSession, *, museum: Museum, year: int = 2023, visitors: int = 8_900_000) -> VisitorRecord`
- `async def build_population_record(session: AsyncSession, *, city: City, year: int = 2023, population: int = 2_100_000) -> PopulationRecord`
**Constraint:** Each factory returns the flushed entity with id populated.
Factories call `session.flush()`, not `commit()`.

### `tests/test_repositories/__init__.py`
Empty.

### `tests/test_repositories/test_city_repository.py`
**Tests (3):**
- `test_upsert_by_qid_inserts_new_city` — assert row created, returns City with id.
- `test_upsert_by_qid_updates_existing_city` — call twice with same QID, different name; assert 1 row in DB, latest name.
- `test_get_by_qid_returns_none_when_missing` — QID not in DB.

### `tests/test_repositories/test_museum_repository.py`
**Tests (3):**
- `test_upsert_by_name_inserts_and_then_updates` — two calls, same name.
- `test_list_paginated_returns_items_and_total` — seed 3 museums, assert `limit=2` returns 2 items, `total=3`.
- `test_list_paginated_eager_loads_city` — seed museum+city, query, assert `m.city.name` doesn't trigger lazy-load (using `inspect(m).unloaded`).

### `tests/test_repositories/test_refresh_state_repository.py`
**Tests (2):**
- `test_get_auto_creates_singleton_on_empty_table` — fresh DB, call `get()`, assert row exists with `id=1, last_refresh_at IS NULL`.
- `test_mark_refreshed_updates_timestamp_and_counts` — call `mark_refreshed(70, 65)`, assert fields set.

## Phase 2 tooling gate

```bash
uv run alembic upgrade head   # against docker compose's db
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest -v              # new tests must pass
uv run lint-imports
```

Expected new test count: 8 (3 + 3 + 2). Cumulative: 19.

## Out of scope for Phase 2

- No services — Phase 3 & 4 consume the repositories.
- No routers.
- No clients.
- No regression logic.
