"""Structured logging setup for the museums application."""

from __future__ import annotations

import logging
import sys
from typing import Final

import structlog

from museums.enums.log_level import LogLevel

_NOISY_LOGGERS = ("httpx", "sqlalchemy.engine", "uvicorn.access")

_LEVELS: Final[dict[LogLevel, int]] = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
}


def _build_shared_processors() -> list[structlog.types.Processor]:
    return [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]


def _build_renderer() -> structlog.types.Processor:
    if sys.stderr.isatty():
        return structlog.dev.ConsoleRenderer()
    return structlog.processors.JSONRenderer()


def _configure_structlog(shared_processors: list[structlog.types.Processor]) -> None:
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _configure_stdlib(shared_processors: list[structlog.types.Processor], level: int) -> None:
    renderer = _build_renderer()
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_logging(level: LogLevel) -> None:
    """Configure structlog with JSON or console rendering.

    Call once from main.py lifespan on startup.
    """
    log_level = _LEVELS[level]
    shared_processors = _build_shared_processors()
    _configure_structlog(shared_processors)
    _configure_stdlib(shared_processors, log_level)
