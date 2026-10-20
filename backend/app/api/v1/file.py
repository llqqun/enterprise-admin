"""文件接口。

下载接口刻意不走 `StorageFile`/静态目录：文件按数据库 id 取，路径永远来自数据库而不是请求参数，
并且一律以 `attachment` 下发 —— 上传的 `.html` 若被内联渲染，就变成了本站源上的 XSS。
"""

from io import BytesIO
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user, require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.file import FileOut
from app.services import file_service

router = APIRouter(prefix="/file", tags=["file"])


def _parse_ids(ids: str) -> list[int]:
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


def _dump(row: Any) -> dict[str, Any]:
    return FileOut.model_validate(row).model_dump()


@router.get("", dependencies=[Depends(require_perm("monitor:file:list"))], summary="文件列表")
async def list_files(
    original_name: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await file_service.list_files(db, params, original_name=original_name)
    return page([_dump(row) for row in rows], total)


@router.post(
    "/upload",
    dependencies=[Depends(require_perm("monitor:file:upload"))],
    summary="上传文件",
)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    row = await file_service.upload(db, file, current)
    return success(_dump(row), msg="上传成功")


@router.get(
    "/download/{file_id}",
    dependencies=[Depends(require_perm("monitor:file:list"))],
    summary="下载文件",
)
async def download_file(file_id: int, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    row, data = await file_service.read_file(db, file_id)
    return StreamingResponse(
        BytesIO(data),
        media_type=row.content_type or "application/octet-stream",
        headers={
            # 强制附件：上传的 html 若被内联渲染就是本站源上的 XSS。
            "Content-Disposition": f'attachment; filename="{row.original_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("monitor:file:remove"))], summary="删除文件"
)
async def delete_files(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await file_service.delete_files(db, _parse_ids(ids))
    return success(msg="删除成功")
