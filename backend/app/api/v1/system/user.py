"""用户接口。

目前只有列表：它是数据权限的第一个（也是验收用的）消费方。增删改属于 P1-A 任务 6。
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_perm
from app.core.response import PageParams, page
from app.db.session import get_db
from app.schemas.system import UserBrief
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
