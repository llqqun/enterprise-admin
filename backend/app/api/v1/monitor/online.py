"""在线用户接口。"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.services import online_service

router = APIRouter(prefix="/online", tags=["monitor:online"])


@router.get(
    "", dependencies=[Depends(require_perm("monitor:online:list"))], summary="在线用户列表"
)
async def list_online(
    user_name: str | None = None,
    login_ip: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await online_service.list_sessions(
        db, params, user_name=user_name, login_ip=login_ip
    )
    return page(rows, total)


@router.delete(
    "/{access_jti}",
    dependencies=[Depends(require_perm("monitor:online:forceLogout"))],
    summary="强制下线",
)
async def force_logout(
    access_jti: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    await online_service.force_logout(db, access_jti, current)
    return success(msg="已强制下线")
