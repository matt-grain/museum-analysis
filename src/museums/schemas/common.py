"""Shared response DTOs: error envelope, pagination meta, health check."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from museums.enums.error_code import ErrorCode


class ErrorOut(BaseModel):
    detail: str
    code: ErrorCode


class PaginationMeta(BaseModel):
    total: int
    skip: int
    limit: int


class HealthOut(BaseModel):
    status: Literal["ok"]
