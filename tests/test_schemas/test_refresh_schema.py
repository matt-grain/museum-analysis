"""Unit tests for RefreshResultOut.from_summary()."""

from __future__ import annotations

from datetime import UTC, datetime

from museums.schemas.refresh import RefreshResultOut
from museums.workflows.ingestion_workflow import RefreshSummary


def _make_summary(started_at: datetime, finished_at: datetime) -> RefreshSummary:
    return RefreshSummary(
        museums_refreshed=2,
        cities_refreshed=2,
        visitor_records_upserted=4,
        population_records_upserted=8,
        started_at=started_at,
        finished_at=finished_at,
    )


def test_from_summary_computes_duration_seconds() -> None:
    # Arrange
    t = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    t_plus_5 = datetime(2024, 1, 1, 12, 0, 5, tzinfo=UTC)
    summary = _make_summary(started_at=t, finished_at=t_plus_5)

    # Act
    result = RefreshResultOut.from_summary(summary)

    # Assert
    assert result.duration_seconds == 5.0
    assert result.museums_refreshed == 2


def test_from_summary_zero_duration_when_start_equals_finish() -> None:
    # Arrange
    t = datetime(2024, 6, 15, 9, 30, 0, tzinfo=UTC)
    summary = _make_summary(started_at=t, finished_at=t)

    # Act
    result = RefreshResultOut.from_summary(summary)

    # Assert
    assert result.duration_seconds == 0.0
