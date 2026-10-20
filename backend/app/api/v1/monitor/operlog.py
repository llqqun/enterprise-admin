"""操作日志接口。

删除接口存在，但被挡在**单独的权限码**之后（`monitor:operlog:remove`），
且删除动作本身会先写一条清理日志 —— 「删日志」这件事也要留痕。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.monitor import OperLogOut
from app.services import oper_log_service

router = APIRouter(prefix="/operlog", tags=["monitor:operlog"])


def _parse_ids(ids: str) -> list[int]:
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


@router.get(
    "", dependencies=[Depends(require_perm("monitor:operlog:list"))], summary="操作日志列表"
)
async def list_oper_logs(
    title: str | None = None,
    oper_name: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await oper_log_service.list_oper_logs(
        db, params, title=title, oper_name=oper_name, status=status
    )
    return page([OperLogOut.model_validate(row).model_dump() for row in rows], total)


@router.delete(
    "/clean", dependencies=[Depends(require_perm("monitor:operlog:remove"))], summary="清空操作日志"
)
async def clean_oper_logs(
    db: AsyncSession = Depends(get_db), current: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    await oper_log_service.clean_oper_logs(db, current)
    return success(msg="清空成功")


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("monitor:operlog:remove"))], summary="删除操作日志"
)
async def delete_oper_logs(
    ids: str,
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    await oper_log_service.delete_oper_logs(db, _parse_ids(ids), current)
    return success(msg="删除成功")
