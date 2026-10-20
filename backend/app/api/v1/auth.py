"""Authentication endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.core.response import success
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    ProfileUpdate,
    RefreshRequest,
    UserProfile,
)
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


@router.put("/profile", summary="修改自己的资料")
async def update_profile(
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """只改昵称/邮箱/手机/性别。

    用户名、状态、部门与角色都不在这里 —— 它们是管理动作，由 `system:user:edit` 保护。
    """
    user = await auth_service.update_own_profile(db, current, payload)
    return success(UserProfile.model_validate(user).model_dump(), msg="修改成功")


@router.put("/password", summary="修改自己的密码")
async def change_password(
    payload: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """需要原密码；成功后其它会话全部失效，当前会话保留。"""
    revoked = await auth_service.change_own_password(db, current, payload)
    return success({"revoked_sessions": revoked}, msg="密码已修改，其他设备的登录已失效")
