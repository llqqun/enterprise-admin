"""system 模块路由聚合。"""

from fastapi import APIRouter

from app.api.v1.system import dept

system_router = APIRouter(prefix="/system")
system_router.include_router(dept.router)
