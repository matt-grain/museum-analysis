# Phase 3 — External Clients & Ingestion Workflow

**Agent:** `python-fastapi`
**Depends on:** Phase 2 (models, repositories, migration).
**Produces for Phase 5:** `MediaWikiClient`, `WikidataClient`, `IngestionWorkflow`.
**Parallelizable with Phase 4** — disjoint files, both depend only on
Phase 2.

**Layer note:** The ingestion code is a **workflow**, not a service.
Rationale: it orchestrates two clients and five repositories inside a
single explicit transaction, and CLAUDE.md forbids services from holding
an `AsyncSession`. Place it at `src/museums/workflows/ingestion_workflow.py`
and register it behind the `workflows/` import-linter contract.

Read `CLAUDE.md` §error-handling carefully — this phase is where most of
that policy becomes concrete. Read `prototype/get_museums_data.py` and
`prototype/get_city_pop.py` for the SPARQL shape (reference only — do not
import or copy verbatim).

## Connection error handling — restated for this phase

1. Every external call uses the shared `retry_policy(settings.http_max_retries)`
   from `http_client.py`.
2. Every client method's final exception type is **domain** (never raw
   `httpx.*`). Wrap: catch `tenacity.RetryError` and tenacity's unwrapping,
   re-raise `MediaWikiUnavailableError` / `WikidataUnavailableError` with
   the original as `__cause__`.
3. Unexpected response shape → `ExternalDataParseError(source=..., detail=...)`.
4. Every client method is covered by a `respx`-backed test that exercises
   the retry path (fail twice, succeed third).

## Files to create (new)

### `src/museums/clients/__init__.py`
Re-export `MediaWikiClient` and `WikidataClient`.

### `src/museums/clients/mediawiki_client.py`
**Purpose:** Fetch the canonical museum list from the Wikipedia list page.
**Class:** `MediaWikiClient`.
**Constructor:** `__init__(self, client: httpx.AsyncClient, settings: Settings)`.
**Public method:**
- `async def fetch_museum_list(self) -> list[MuseumListEntry]` — returns
  parsed entries.
**DTO (in same file, dataclass):**
```python
@dataclass(frozen=True)
class MuseumListEntry:
    wikipedia_title: str   # e.g. "Louvre"
    display_name: str      # the visible link text; often same as title
```
**Approach (Action API):**
- Call `GET {mediawiki_base_url}?action=parse&page={settings.wikipedia_list_page_title}&format=json&prop=wikitext&redirects=1`.
- Parse `response.json()["parse"]["wikitext"]["*"]` (MediaWiki wikitext).
- Use `mwparserfromhell.parse(wikitext)` to build a structured node tree.
  Iterate through the top-level sortable tables (wikitable class) — the
  list page has one primary table per "most visited museums" year
  variant; walk all tables. For each `{{|-}}` row, extract the first
  `Wikilink` node (title + display text) — that's the museum.
- Filter out non-museum wikilinks: skip wikilinks whose title starts with
  `File:`, `Image:`, `Category:`, or whose display text is a number
  (visitor-count cells).
- Deduplicate by `wikipedia_title` (case-insensitive, trimmed).
**Error handling:**
- Wrap the HTTP call in the tenacity retry policy. On `RetryError`, raise
  `MediaWikiUnavailableError(service_name="mediawiki")`.
- On JSON decode failure or missing `parse.wikitext.*` key, raise
  `ExternalDataParseError(source="mediawiki", detail=...)`.
- On empty parsed list (< 10 entries), raise `ExternalDataParseError`
  — the list page should have >50 entries; tiny results indicate the
  parser is broken or the page layout changed.
**User-Agent:** Use `settings.user_agent` on every request.
**Constraint:** Do NOT scrape rendered HTML. Use Action API `wikitext`
response — more stable. If parsing wikitext proves flaky, fall back to
`action=parse&prop=sections` to find the right section first, then
re-request `prop=wikitext&section=N`.

### `src/museums/clients/wikidata_client.py`
**Purpose:** Fetch structured data for museums and cities via SPARQL.
**Class:** `WikidataClient`.
**Constructor:** `__init__(self, client: httpx.AsyncClient, settings: Settings)`.
**Public methods:**
- `async def fetch_museum_enrichment(self, titles: Sequence[str]) -> list[MuseumEnrichment]` — resolves Wikipedia titles → Wikidata QIDs → museum details + visitor records. Batch titles in groups of 50 (SPARQL VALUES clause).
- `async def fetch_city_populations(self, city_qids: Sequence[str]) -> dict[str, list[PopulationPoint]]` — for each city QID, return its time-series population points (year ≥ 2000 only). Batch QIDs in groups of 50.
**DTOs (dataclasses frozen, in same file):**
```python
@dataclass(frozen=True)
class MuseumEnrichment:
    wikipedia_title: str
    museum_qid: str
    museum_label: str
    city_qid: str | None
    city_label: str | None
    country_label: str | None
    visitor_records: list[VisitorPoint]  # zero or more

@dataclass(frozen=True)
class VisitorPoint:
    year: int
    visitors: int

@dataclass(frozen=True)
class PopulationPoint:
    year: int
    population: int
```
**SPARQL query for museum enrichment (parameterize VALUES with titles):**
- Resolve Wikipedia article titles → QIDs using the `schema:about` triple
  pattern (a single SPARQL query, no federated `SERVICE` clause):
  `?article schema:about ?museum ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title . VALUES ?title { "Louvre"@en "British Museum"@en ... }`.
- From the resolved QID: grab P1174 (visitors) with P585 (year),
  P131/P159 (city), P17 (country). Filter visitors >
  `settings.museum_visitor_threshold`.
- Filter year ≥ 2000.
- See `prototype/get_museums_data.py` for the general SPARQL shape —
  replace the `?museum wdt:P31/wdt:P279* wd:Q33506` opener with the
  `schema:about` resolver above.
**SPARQL query for city populations:**
- Input `VALUES ?city { wd:Q90 wd:Q60 ... }`.
- P1082 (population) with P585 (year), `FILTER(YEAR(?date) >= 2000)`.
- For duplicates in same year, keep max.
**Error handling:**
- Use `Accept: application/sparql-results+json` header on every request.
- Wrap HTTP call in retry policy → on `RetryError`, raise
  `WikidataUnavailableError`.
- On malformed JSON or missing `results.bindings`, raise
  `ExternalDataParseError(source="wikidata", detail=...)`.
- Partial results are acceptable: if a batch of 50 QIDs returns fewer
  populations than expected, that's normal (not all cities have data).
  But if ALL batches return zero, raise `ExternalDataParseError`.
**Batching:** `def _chunk(seq: Sequence[T], size: int = 50) -> Iterator[list[T]]`.
**User-Agent:** Required by Wikidata ToS. Use `settings.user_agent`.

### `src/museums/services/__init__.py`
Empty package marker for Phase 3 (services land in Phase 4).

### `src/museums/workflows/__init__.py`
Re-export `IngestionWorkflow`, `IngestionDeps`, `RefreshSummary`.

### `src/museums/workflows/ingestion_workflow.py`
**Purpose:** Orchestrate the refresh under a single explicit transaction:
call clients, upsert via repositories, mark state. This is the one layer
allowed to hold an `AsyncSession`.
**Classes:**

```python
@dataclass(slots=True, frozen=True)
class IngestionDeps:
    city_repo: CityRepository
    museum_repo: MuseumRepository
    visitor_repo: VisitorRecordRepository
    population_repo: PopulationRecordRepository
    refresh_repo: RefreshStateRepository

class IngestionWorkflow:
    def __init__(
        self,
        mediawiki: MediaWikiClient,
        wikidata: WikidataClient,
        session: AsyncSession,
        settings: Settings,
        deps: IngestionDeps,
    ) -> None: ...
```

Constructor is now 5 arguments — within the CLAUDE.md limit.
`IngestionDeps` is built inside `dependencies.py` (Phase 5) from the
individual repo `Depends()` factories.

**Public method:**
```python
async def refresh(self, *, force: bool) -> RefreshSummary: ...
```
**DTO (in same file):**
```python
@dataclass(frozen=True)
class RefreshSummary:
    museums_refreshed: int
    cities_refreshed: int
    visitor_records_upserted: int
    population_records_upserted: int
    started_at: datetime
    finished_at: datetime
```

**Algorithm:**
1. Read `refresh_state`. If `last_refresh_at` is not None and
   `(now - last_refresh_at) < cooldown` and `not force`:
   raise `RefreshCooldownError(remaining_seconds=...)`.
2. `titles = await mediawiki.fetch_museum_list()` — list of `MuseumListEntry`.
3. `enrichments = await wikidata.fetch_museum_enrichment([e.wikipedia_title for e in titles])`.
4. Build unique city QID set from enrichments; fetch
   `populations = await wikidata.fetch_city_populations(unique_city_qids)`.
5. BEGIN the outer transaction (already open via `session`):
   a. For each enrichment with a `city_qid`: `city = await self._deps.city_repo.upsert_by_qid(...)`; collect into `qid_to_city_id`.
   b. For each enrichment: `museum = await self._deps.museum_repo.upsert_by_name(name=enrichment.museum_label, wikipedia_title=enrichment.wikipedia_title, wikidata_qid=enrichment.museum_qid, city_id=qid_to_city_id.get(enrichment.city_qid), country=enrichment.country_label)`.
   c. Bulk upsert visitor records per museum (via `self._deps.visitor_repo`).
   d. Bulk upsert population records per city (via `self._deps.population_repo`).
   e. `await self._deps.refresh_repo.mark_refreshed(museums=..., cities=...)`.
6. `await self._session.commit()`. On any exception raised during steps 2–5,
   call `await self._session.rollback()` and re-raise.
7. Return `RefreshSummary`.

**Error handling:**
- `RefreshCooldownError` → propagated (caught by router in Phase 5).
- `MediaWikiUnavailableError` / `WikidataUnavailableError` → propagated.
- Any other unexpected exception → rollback, log at ERROR with a
  correlation id, re-raise.
**Logging:** Use `structlog.get_logger("ingestion")`; log at INFO at each
step boundary with counts.

## Test files

### `tests/fixtures/__init__.py`
Empty (package marker so fixtures can be loaded relative to tests).

### `tests/fixtures/wikitext_fixture.txt`
Trimmed excerpt of the real `List_of_most_visited_museums` page (fetch
live via `curl` during plan implementation, keep 3 museum rows + the
surrounding table markup). ~40 lines of wikitext.

### `tests/fixtures/wikidata_museum_enrichment.json`
Sample SPARQL JSON response shaped like:
`{"head": {"vars": [...]}, "results": {"bindings": [ ... 2 museums × 2 years ... ]}}`.
Handwritten based on the actual Wikidata schema. ~40 lines.

### `tests/fixtures/wikidata_city_populations.json`
Similar: 2 cities × 2 years each, 4 bindings total.

### `tests/test_clients/__init__.py`
Empty.

### `tests/test_clients/test_mediawiki_client.py`
**Tests (3):**
- `test_fetch_museum_list_parses_entries_happy_path` — `respx` returns a
  fixture wikitext with 3 museum rows; assert 3 entries returned.
- `test_fetch_museum_list_retries_on_503_then_succeeds` — `respx` returns
  503 twice, then success; assert success & 3 attempts made.
- `test_fetch_museum_list_raises_mediawiki_unavailable_after_max_retries` — `respx`
  always-503; assert `pytest.raises(MediaWikiUnavailableError)` and the
  original `httpx.HTTPStatusError` is `__cause__`.
**Fixtures:** `wikitext_fixture.txt` in `tests/fixtures/` — a trimmed
sample of the real list page with 3 rows.

### `tests/test_clients/test_wikidata_client.py`
**Tests (3):**
- `test_fetch_museum_enrichment_parses_sparql_results` — `respx` returns
  a JSON fixture matching Wikidata SPARQL shape for 2 museums; assert
  `MuseumEnrichment` objects built correctly (years, visitors, city QIDs).
- `test_fetch_city_populations_groups_by_qid` — input 2 city QIDs, fixture
  returns 4 rows (2 per city, different years); assert dict has 2 keys,
  each with 2 `PopulationPoint`s sorted by year.
- `test_fetch_raises_external_data_parse_error_on_missing_bindings` — `respx`
  returns `{"results": {}}` (no bindings); assert `ExternalDataParseError`
  raised with `source="wikidata"`.
**Fixtures:** `tests/fixtures/wikidata_museum_enrichment.json`,
`tests/fixtures/wikidata_city_populations.json`.

### `tests/test_services/__init__.py`
Empty (populated by Phase 4's harmonization/regression tests).

### `tests/test_workflows/__init__.py`
Empty.

### `tests/test_workflows/test_ingestion_workflow.py`
**Tests (5):**
- `test_refresh_persists_all_entities_on_happy_path` — stub clients return
  fixture data; run `refresh(force=False)`; assert rows in all 5 tables
  + `refresh_state.last_refresh_at` set.
- `test_refresh_within_cooldown_raises_refresh_cooldown_error` — seed
  `refresh_state.last_refresh_at = now()`; call `refresh(force=False)`;
  assert `RefreshCooldownError` raised with expected `retry_after_seconds`.
- `test_refresh_with_force_bypasses_cooldown` — same as above but
  `force=True`; assert completes and updates `last_refresh_at`.
- `test_refresh_rolls_back_on_client_failure` — stub mediawiki success,
  wikidata raises `WikidataUnavailableError`; assert no rows in `museums`
  or `cities` tables (rollback), `last_refresh_at` unchanged.
- `test_refresh_upserts_idempotently_on_second_run` — call `refresh` twice
  with same fixture data; assert no duplicate rows.
**Stubs:** Use `unittest.mock.AsyncMock` (or a small handwritten stub) for
`MediaWikiClient` / `WikidataClient` — NOT `respx`. `respx` is for
testing clients; service tests should stub the client layer directly.

## Phase 3 tooling gate

```bash
uv run pyright .
uv run ruff check . --fix
uv run ruff format .
uv run pytest -v
uv run lint-imports
```

Expected new tests: 11 (3 + 3 + 5). Cumulative: 30.

## Out of scope for Phase 3

- No routers.
- No harmonization / regression (Phase 4).
- No notebook.
- `src/museums/dependencies.py` not touched yet — Phase 5 wires clients
  and services.
