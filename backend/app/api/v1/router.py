"""Aggregate router for API v1."""

from fastapi import APIRouter

from app.api.v1 import auth
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().API_V1_PREFIX)
api_router.include_router(auth.router)
