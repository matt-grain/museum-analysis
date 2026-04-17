"""ErrorCode enum — closed set of API error codes returned in ErrorOut.code."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    REFRESH_COOLDOWN = "refresh_cooldown"
    EXTERNAL_UNAVAILABLE = "external_unavailable"
    EXTERNAL_PARSE_ERROR = "external_parse_error"
    INSUFFICIENT_DATA = "insufficient_data"
