"""system 模块路由聚合。"""

from fastapi import APIRouter

from app.api.v1.system import config, dept, dict, menu, notice, post, role, user

system_router = APIRouter(prefix="/system")
system_router.include_router(dept.router)
system_router.include_router(post.router)
system_router.include_router(menu.router)
system_router.include_router(role.router)
system_router.include_router(user.router)
system_router.include_router(dict.router)
system_router.include_router(config.router)
system_router.include_router(notice.router)
