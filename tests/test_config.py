"""Tests for src/museums/config.py."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from museums.config import Settings, get_settings


def test_settings_loads_defaults_from_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings picks up MUSEUMS_-prefixed env vars correctly."""
    monkeypatch.setenv("MUSEUMS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MUSEUMS_REFRESH_COOLDOWN_HOURS", "48")

    s = Settings()

    assert s.log_level == "DEBUG"
    assert s.refresh_cooldown_hours == 48


def test_settings_rejects_invalid_cooldown_hours() -> None:
    """refresh_cooldown_hours=0 must fail validation (ge=1)."""
    with pytest.raises(ValidationError):
        Settings(refresh_cooldown_hours=0)  # type: ignore[call-arg]


def test_settings_rejects_invalid_log_level() -> None:
    """log_level must match the allowed pattern — TRACE is not valid."""
    with pytest.raises(ValidationError):
        Settings(log_level="TRACE")  # type: ignore[call-arg]


def test_get_settings_is_memoized() -> None:
    """Two calls to get_settings() return the exact same instance."""
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
