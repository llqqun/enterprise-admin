"""通知公告接口。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.notice import NoticeCreate, NoticeOut, NoticeUpdate
from app.services import notice_service

router = APIRouter(prefix="/notice", tags=["system:notice"])


def _parse_ids(ids: str) -> list[int]:
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


@router.get("", dependencies=[Depends(require_perm("system:notice:list"))], summary="公告列表")
async def list_notices(
    notice_title: str | None = None,
    notice_type: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await notice_service.list_notices(
        db, params, notice_title=notice_title, notice_type=notice_type, status=status
    )
    return page([NoticeOut.model_validate(row).model_dump() for row in rows], total)


@router.get("/latest", summary="最新公告（首页用，只要求登录）")
async def latest(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """只返回**已发布**的公告。撤回的公告出现在首页等于没撤回。"""
    rows = await notice_service.latest_notices(db)
    return success([NoticeOut.model_validate(row).model_dump() for row in rows])


@router.get(
    "/{notice_id}", dependencies=[Depends(require_perm("system:notice:query"))], summary="公告详情"
)
async def get_notice(notice_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(NoticeOut.model_validate(await notice_service.get_notice(db, notice_id)).model_dump())


@router.post("", dependencies=[Depends(require_perm("system:notice:add"))], summary="新增公告")
async def create_notice(payload: NoticeCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(NoticeOut.model_validate(await notice_service.create_notice(db, payload)).model_dump(), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:notice:edit"))], summary="修改公告")
async def update_notice(payload: NoticeUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(NoticeOut.model_validate(await notice_service.update_notice(db, payload)).model_dump(), msg="修改成功")


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("system:notice:remove"))], summary="删除公告"
)
async def delete_notices(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await notice_service.delete_notices(db, _parse_ids(ids))
    return success(msg="删除成功")
