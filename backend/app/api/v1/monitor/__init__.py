"""监控模块路由聚合。"""

from fastapi import APIRouter

from app.api.v1.monitor import loginlog

monitor_router = APIRouter(prefix="/monitor")
monitor_router.include_router(loginlog.router)
