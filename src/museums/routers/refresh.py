"""Refresh router — triggers a full data ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from museums.dependencies import IngestionWorkflowDep
from museums.schemas.refresh import RefreshResultOut

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post(
    "",
    response_model=RefreshResultOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a full data refresh",
    description=(
        "Re-ingests the canonical museum list from the MediaWiki Action API "
        "and enriches each entry with Wikidata SPARQL (city, visitor counts, country) "
        "plus per-city population history. The refresh replaces existing data atomically — "
        "if any external call fails, the DB rolls back to its pre-refresh state. "
        "Blocked by a 24h cooldown unless `force=true`."
    ),
    responses={
        429: {"description": ("Cooldown active. Retry-After header indicates seconds until next attempt.")},
        502: {"description": "Upstream API returned an unexpected shape (parse error)."},
        503: {"description": "MediaWiki or Wikidata is unreachable after retries."},
    },
)
async def refresh(
    workflow: IngestionWorkflowDep,
    force: bool = Query(default=False, description="Bypass the cooldown check."),
) -> RefreshResultOut:
    """Trigger a full museum + city data refresh."""
    summary = await workflow.refresh(force=force)
    return RefreshResultOut.from_summary(summary)
