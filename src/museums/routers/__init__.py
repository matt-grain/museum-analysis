"""Central API router aggregating all domain routers."""

from __future__ import annotations

from fastapi import APIRouter

from museums.routers.cities import router as cities_router
from museums.routers.harmonized import router as harmonized_router
from museums.routers.health import router as health_router
from museums.routers.museums import router as museums_router
from museums.routers.refresh import router as refresh_router
from museums.routers.regression import router as regression_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(refresh_router)
api_router.include_router(museums_router)
api_router.include_router(cities_router)
api_router.include_router(harmonized_router)
api_router.include_router(regression_router)
