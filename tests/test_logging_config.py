"""Smoke tests for museums.logging_config."""

from __future__ import annotations

import logging

from museums.enums.log_level import LogLevel
from museums.logging_config import setup_logging


def test_setup_logging_sets_root_logger_to_requested_level() -> None:
    setup_logging(LogLevel.DEBUG)
    assert logging.getLogger().level == logging.DEBUG
