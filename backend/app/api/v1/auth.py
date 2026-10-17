"""Authentication endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success
from app.db.session import get_db
from app.schemas.auth import LoginRequest
from app.services import auth_service
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
