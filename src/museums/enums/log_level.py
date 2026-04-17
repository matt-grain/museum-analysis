"""LogLevel enum — discrete log level values used in Settings and logging_config."""

from __future__ import annotations

from enum import StrEnum


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
