"""Refresh result response DTO."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from museums.workflows.ingestion_workflow import RefreshSummary


class RefreshResultOut(BaseModel):
    museums_refreshed: int
    cities_refreshed: int
    visitor_records_upserted: int
    population_records_upserted: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float

    @classmethod
    def from_summary(cls, summary: RefreshSummary) -> RefreshResultOut:
        """Build a RefreshResultOut from a RefreshSummary domain object."""
        duration = (summary.finished_at - summary.started_at).total_seconds()
        return cls(
            museums_refreshed=summary.museums_refreshed,
            cities_refreshed=summary.cities_refreshed,
            visitor_records_upserted=summary.visitor_records_upserted,
            population_records_upserted=summary.population_records_upserted,
            started_at=summary.started_at,
            finished_at=summary.finished_at,
            duration_seconds=duration,
        )
