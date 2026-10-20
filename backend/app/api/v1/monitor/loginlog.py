"""登录日志接口。"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import PageParams, page
from app.db.session import get_db
from app.schemas.monitor import LoginLogOut
from app.services import login_log_service

router = APIRouter(prefix="/loginlog", tags=["monitor:loginlog"])


@router.get(
    "", dependencies=[Depends(require_perm("monitor:loginlog:list"))], summary="登录日志列表"
)
async def list_login_logs(
    user_name: str | None = None,
    status: str | None = None,
    begin_date: str | None = None,
    end_date: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await login_log_service.list_login_logs(
        db,
        params,
        user_name=user_name,
        status=status,
        begin_date=begin_date,
        end_date=end_date,
    )
    return page([LoginLogOut.model_validate(row).model_dump() for row in rows], total)
