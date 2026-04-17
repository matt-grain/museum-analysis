"""Refresh router — triggers a full data ingestion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from museums.dependencies import IngestionWorkflowDep, SettingsDep
from museums.schemas.refresh import RefreshResultOut

router = APIRouter(prefix="/refresh", tags=["refresh"])


async def _require_refresh_key(
    settings: SettingsDep,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Validate the X-API-Key header against Settings.refresh_api_key.

    No-op when MUSEUMS_REFRESH_API_KEY is unset (the default — local dev /
    docker compose is open). When set, missing or mismatched header -> 401.
    """
    if settings.refresh_api_key is None:
        return
    if x_api_key != settings.refresh_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )


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
        "Blocked by a 24h cooldown unless `force=true`. "
        "Requires X-API-Key header when MUSEUMS_REFRESH_API_KEY is set in the environment."
    ),
    dependencies=[Depends(_require_refresh_key)],
    responses={
        401: {"description": "Missing or invalid X-API-Key header (only when auth is enabled)."},
        429: {"description": "Cooldown active. Retry-After header indicates seconds until next attempt."},
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
