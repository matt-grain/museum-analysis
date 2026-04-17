# Architecture Diagrams

GitHub renders Mermaid natively, so these diagrams display inline when
browsing the repo. Local preview: `scripts/generate_diagrams.py` renders
each block to an SVG under `docs/diagrams/` via `npx
@mermaid-js/mermaid-cli`.

## Class Diagram — Layered Architecture

High-level view of the `src/museums/` module layout: data → repositories
→ services/workflows → routers + schemas, with clients as a side-branch
for external APIs.

```mermaid
classDiagram
    direction TB

    class Museum {
        +int id
        +str name
        +str wikipedia_title
        +str? wikidata_qid
        +int? city_id
        +list~VisitorRecord~ visitor_records
        +City? city
    }
    class City {
        +int id
        +str wikidata_qid
        +str name
        +str? country
        +list~PopulationRecord~ population_records
    }
    class VisitorRecord {
        +int museum_id
        +int year
        +int visitors
    }
    class PopulationRecord {
        +int city_id
        +int year
        +int population
    }
    class RefreshState {
        +int id (=1)
        +datetime? last_refresh_at
    }

    class MuseumRepository {
        +list_paginated(skip, limit) tuple
        +upsert_by_name(...) Museum
        +delete_all() None
    }
    class CityRepository {
        +upsert_by_qid(...) City
        +list_all() list
        +delete_all() None
    }
    class HealthRepository {
        +ping() None
    }

    class HarmonizationService {
        -museum_repo
        -visitor_repo
        -population_repo
        +build_harmonized_rows() list~HarmonizedRow~
        +build_harmonized_paginated(skip, limit) PaginatedHarmonizedOut
    }
    class RegressionService {
        -harmonization
        +fit() RegressionResult
    }
    class MuseumQueryService {
        +list_paginated(skip, limit) PaginatedMuseumsOut
    }
    class CityQueryService {
        +list_paginated(skip, limit) PaginatedCitiesOut
    }
    class HealthService {
        -repo: HealthRepository
        +check() None
    }

    class IngestionWorkflow {
        -mediawiki: MediaWikiClient
        -wikidata: WikidataClient
        -session: AsyncSession
        -settings: Settings
        -deps: IngestionDeps
        +refresh(force) RefreshSummary
    }
    class IngestionDeps {
        <<dataclass>>
        +CityRepository city_repo
        +MuseumRepository museum_repo
        +VisitorRecordRepository visitor_repo
        +PopulationRecordRepository population_repo
        +RefreshStateRepository refresh_repo
    }

    class MediaWikiClient {
        +fetch_museum_list() list~MuseumListEntry~
    }
    class WikidataClient {
        +fetch_museum_enrichment(titles) list
        +fetch_city_populations(qids) dict
    }

    Museum "1" --> "*" VisitorRecord : has
    City "1" --> "*" PopulationRecord : has
    Museum "*" --> "0..1" City : located in

    MuseumRepository ..> Museum
    CityRepository ..> City
    HealthRepository ..> City : SELECT 1

    HarmonizationService --> MuseumRepository
    HarmonizationService --> CityRepository : via population_repo
    RegressionService --> HarmonizationService : composes
    MuseumQueryService --> MuseumRepository
    CityQueryService --> CityRepository
    HealthService --> HealthRepository

    IngestionWorkflow --> IngestionDeps : owns
    IngestionWorkflow --> MediaWikiClient
    IngestionWorkflow --> WikidataClient
    IngestionDeps --> CityRepository
    IngestionDeps --> MuseumRepository
```

## Sequence Diagram — `POST /refresh?force=false`

The full ingestion path, including the cooldown guard, transactional
wipe-before-insert, and rollback on upstream failure.

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Router as refresh router
    participant Workflow as IngestionWorkflow
    participant RefreshRepo as RefreshStateRepository
    participant MW as MediaWikiClient
    participant WD as WikidataClient
    participant DB as Repositories + DB

    Client->>Router: POST /refresh?force=false
    Router->>Workflow: refresh(force=false)

    Workflow->>RefreshRepo: get()
    RefreshRepo-->>Workflow: RefreshState

    alt Within 24h cooldown
        Workflow-->>Router: raise RefreshCooldownError
        Router-->>Client: 429 + Retry-After
    else Cooldown passed (or force=true)
        Workflow->>MW: fetch_museum_list()
        MW-->>Workflow: list[MuseumListEntry]

        Workflow->>WD: fetch_museum_enrichment(titles)
        WD-->>Workflow: list[MuseumEnrichment]

        Workflow->>WD: fetch_city_populations(city_qids)
        WD-->>Workflow: dict[qid -> list[PopulationPoint]]

        Note over Workflow,DB: All DB writes wrapped<br/>in one transaction

        Workflow->>DB: museum_repo.delete_all()
        Workflow->>DB: city_repo.delete_all() (FK CASCADE on children)
        Workflow->>DB: upsert cities / museums / visitors / populations
        Workflow->>RefreshRepo: mark_refreshed(counts)

        alt Any exception during steps 3-7
            Workflow->>DB: session.rollback()
            Workflow-->>Router: re-raise domain error
            Router-->>Client: 502 / 503 via exception handlers
        else All steps succeed
            Workflow->>DB: session.commit()
            Workflow-->>Router: RefreshSummary
            Router-->>Client: 202 + RefreshResultOut
        end
    end
```

## Sequence Diagram — `GET /regression`

Read-side pipeline: harmonization fits per-city OLS, regression fits
log-log OLS on the harmonized output.

```mermaid
sequenceDiagram
    autonumber
    participant Client
    participant Router as regression router
    participant RegSvc as RegressionService
    participant HarmSvc as HarmonizationService
    participant MRepo as MuseumRepository
    participant PRepo as PopulationRecordRepository

    Client->>Router: GET /regression
    Router->>RegSvc: fit()
    RegSvc->>HarmSvc: build_harmonized_rows()

    HarmSvc->>MRepo: list_paginated(0, 10_000)
    MRepo-->>HarmSvc: museums with city + visitor_records
    HarmSvc->>PRepo: list_all_grouped()
    PRepo-->>HarmSvc: dict[city_id -> list[PopulationRecord]]

    Note over HarmSvc: Per-city OLS fit<br/>(numpy.polyfit deg=1)

    loop For each eligible museum
        HarmSvc->>HarmSvc: pick most-recent visitor record
        HarmSvc->>HarmSvc: project population_est at visitor_year
        HarmSvc->>HarmSvc: flag population_is_extrapolated
    end

    HarmSvc-->>RegSvc: list[HarmonizedRow]

    alt fewer than 5 rows
        RegSvc-->>Router: raise InsufficientDataError
        Router-->>Client: 422 + code=insufficient_data
    else >= 5 rows
        Note over RegSvc: sklearn LinearRegression<br/>on log(population) vs log(visitors)
        RegSvc->>RegSvc: compute R², residuals, per-point predictions
        RegSvc-->>Router: RegressionResult
        Router-->>Client: 200 + RegressionResultOut
    end
```

## Data Flow — End-to-end view

From Wikipedia raw page all the way to the notebook's regression plot.

```mermaid
flowchart LR
    Wiki[en.wikipedia.org<br/>List_of_most_visited_museums]
    WD[query.wikidata.org<br/>SPARQL endpoint]
    Parser[mwparserfromhell<br/>parse wikitext]

    Wiki -->|Action API<br/>action=parse&prop=wikitext| Parser
    Parser -->|list of Wikipedia titles| MWClient[MediaWikiClient]

    WD -->|SPARQL schema:about +<br/>P131* walk to Q515| WDClient[WikidataClient]

    MWClient -->|titles| Workflow[IngestionWorkflow]
    WDClient -->|enrichments<br/>populations| Workflow

    Workflow -->|wipe + upsert in one tx| PG[(PostgreSQL)]
    PG -->|read| HarmSvc[HarmonizationService]
    HarmSvc -->|per-city OLS fit| RegSvc[RegressionService]
    RegSvc -->|log-log OLS| NB[Jupyter Notebook]

    subgraph Filters[Data cleanup]
        OutlierFilter[filter_scope_outliers<br/>drop >2x min when max/min > 2]
        NearestYear[pick most-recent visitor record]
        P131Walk[P131* walk up to Q515<br/>Louvre → Paris, not arrondissement]
    end

    Parser -.-> P131Walk
    WDClient -.-> OutlierFilter
    HarmSvc -.-> NearestYear
```

## Refresh Policy — State Machine

`RefreshState` itself is not an FSM per our architectural rules (no
`status` field), but the refresh operation has a clear state machine
around the 24h cooldown.

```mermaid
stateDiagram-v2
    [*] --> NeverRefreshed
    NeverRefreshed --> Refreshing: POST /refresh<br/>(any time)
    Fresh --> Refreshing: POST /refresh?force=true
    Fresh --> Cooling: POST /refresh<br/>(< 24h since last)
    Cooling --> Fresh: 429<br/>Retry-After returned<br/>no state change
    Refreshing --> Fresh: commit + mark_refreshed
    Refreshing --> Stale: rollback on failure<br/>(pre-refresh state restored)
    Stale --> Refreshing: POST /refresh?force=true

    state Refreshing {
        [*] --> FetchMediaWiki
        FetchMediaWiki --> FetchEnrichment
        FetchEnrichment --> FetchPopulations
        FetchPopulations --> WipeExisting: after fetch succeeds
        WipeExisting --> UpsertAll
        UpsertAll --> MarkRefreshed
        MarkRefreshed --> [*]: commit
    }
```
