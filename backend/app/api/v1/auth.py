"""Authentication endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.core.response import success
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RefreshRequest
from app.services import auth_service, menu_service
from app.utils.request_info import client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/captchaImage", summary="获取图形验证码")
async def captcha_image() -> dict[str, Any]:
    return success(await auth_service.build_captcha())


@router.post("/login", summary="登录并获取令牌")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await auth_service.authenticate(
        db,
        payload,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    return success(result, msg="登录成功")


@router.get("/profile", summary="获取当前用户信息、角色与权限")
async def profile(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return success(await auth_service.build_profile(db, current))


@router.post("/refresh", summary="用刷新令牌换取新的令牌对")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return success(await auth_service.refresh_tokens(db, payload.refresh_token))


@router.get("/routers", summary="获取当前用户的动态路由")
async def routers(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return success(await menu_service.get_routers(db, current))


@router.post("/logout", summary="退出登录并使当前令牌立即失效")
async def logout(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await auth_service.revoke_by_access_jti(db, current.access_jti)
    return success(msg="退出成功")
