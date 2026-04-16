"""Refresh router — triggers a full data ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from museums.dependencies import IngestionWorkflowDep
from museums.schemas.refresh import RefreshResultOut

router = APIRouter(prefix="/refresh", tags=["refresh"])


@router.post("", response_model=RefreshResultOut, status_code=status.HTTP_202_ACCEPTED)
async def refresh(
    workflow: IngestionWorkflowDep,
    force: bool = Query(default=False, description="Bypass the cooldown check."),
) -> RefreshResultOut:
    """Trigger a full museum + city data refresh."""
    summary = await workflow.refresh(force=force)
    return RefreshResultOut.from_summary(summary)
