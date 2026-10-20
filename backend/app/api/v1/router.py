"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1 import auth
from app.api.v1.monitor import monitor_router
from app.api.v1.system import system_router
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().API_V1_PREFIX)
api_router.include_router(auth.router)
api_router.include_router(system_router)
api_router.include_router(monitor_router)
