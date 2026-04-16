"""Shared response DTOs: error envelope, pagination meta, health check."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ErrorOut(BaseModel):
    detail: str
    code: str


class PaginationMeta(BaseModel):
    total: int
    skip: int
    limit: int


class HealthOut(BaseModel):
    status: Literal["ok"]
