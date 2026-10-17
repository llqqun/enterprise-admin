"""岗位接口。

`/optionselect` 必须声明在 `/{post_id}` 之前，否则它会被当成 `post_id` 解析。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.system import PostCreate, PostOption, PostOut, PostUpdate
from app.services import post_service

router = APIRouter(prefix="/post", tags=["system:post"])


def _dump(post: Any) -> dict[str, Any]:
    return PostOut.model_validate(post).model_dump()


def _parse_ids(ids: str) -> list[int]:
    """`1,2,3` → `[1, 2, 3]`。

    格式不对时给 422 而不是 500：这是调用方的输入问题，不是一个意外。
    """
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


@router.get("", dependencies=[Depends(require_perm("system:post:list"))], summary="岗位列表")
async def list_posts(
    post_code: str | None = None,
    post_name: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await post_service.list_posts(
        db, params, post_code=post_code, post_name=post_name, status=status
    )
    return page([_dump(row) for row in rows], total)


@router.get(
    "/optionselect", dependencies=[Depends(require_perm("system:post:list"))], summary="岗位下拉"
)
async def post_options(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    posts = await post_service.post_options(db)
    return success([PostOption.model_validate(post).model_dump() for post in posts])


@router.get("/{post_id}", dependencies=[Depends(require_perm("system:post:query"))], summary="岗位详情")
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await post_service.get_post(db, post_id)))


@router.post("", dependencies=[Depends(require_perm("system:post:add"))], summary="新增岗位")
async def create_post(payload: PostCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await post_service.create_post(db, payload)), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:post:edit"))], summary="修改岗位")
async def update_post(payload: PostUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await post_service.update_post(db, payload)), msg="修改成功")


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("system:post:remove"))], summary="删除岗位"
)
async def delete_posts(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await post_service.delete_posts(db, _parse_ids(ids))
    return success(msg="删除成功")
