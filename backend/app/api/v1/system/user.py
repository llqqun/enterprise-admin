"""用户接口。

目前只有列表：它是数据权限的第一个（也是验收用的）消费方。增删改属于 P1-A 任务 6。
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.system import (
    UserBrief,
    UserCreate,
    UserResetPwd,
    UserStatusChange,
    UserUpdate,
)
from app.services import user_service

router = APIRouter(prefix="/user", tags=["system:user"])


@router.get("", dependencies=[Depends(require_perm("system:user:list"))], summary="用户列表")
async def list_users(
    user_name: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    rows, total = await user_service.list_users(
        db, params, current, user_name=user_name, status=status
    )
    return page([UserBrief.model_validate(row).model_dump() for row in rows], total)


def _parse_ids(ids: str) -> list[int]:
    from fastapi import HTTPException

    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


def _dump(user: Any) -> dict[str, Any]:
    """`UserBrief` 里没有 password 字段 —— 这是结构上的保证，不是靠记得删。"""
    return UserBrief.model_validate(user).model_dump()


@router.post("", dependencies=[Depends(require_perm("system:user:add"))], summary="新增用户")
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await user_service.create_user(db, payload)), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:user:edit"))], summary="修改用户")
async def update_user(payload: UserUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await user_service.update_user(db, payload)), msg="修改成功")


@router.put(
    "/resetPwd", dependencies=[Depends(require_perm("system:user:edit"))], summary="重置密码"
)
async def reset_password(
    payload: UserResetPwd, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    await user_service.reset_password(db, payload.user_id, payload.password)
    return success(msg="重置成功")


@router.put(
    "/changeStatus", dependencies=[Depends(require_perm("system:user:edit"))], summary="启用/停用"
)
async def change_status(
    payload: UserStatusChange,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    await user_service.change_status(db, payload.user_id, payload.status, current)
    return success(msg="修改成功")


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("system:user:remove"))], summary="删除用户"
)
async def delete_users(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    await user_service.delete_users(db, _parse_ids(ids), current)
    return success(msg="删除成功")