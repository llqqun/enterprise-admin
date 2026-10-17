"""部门接口。

路由顺序有讲究：`/treeselect` 必须声明在 `/{dept_id}` **之前**，否则 "treeselect" 会被当成
`dept_id` 解析并返回 422。FastAPI 按声明顺序匹配。
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import page, success
from app.db.session import get_db
from app.schemas.system import DeptCreate, DeptOut, DeptUpdate
from app.services import dept_service

router = APIRouter(prefix="/dept", tags=["system:dept"])


def _dump(dept: Any) -> dict[str, Any]:
    return DeptOut.model_validate(dept).model_dump()


@router.get("", dependencies=[Depends(require_perm("system:dept:list"))], summary="部门列表（树）")
async def list_depts(
    dept_name: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await dept_service.list_depts(db, dept_name=dept_name, status=status)
    return page(rows, total)


@router.get(
    "/treeselect",
    dependencies=[Depends(require_perm("system:dept:list"))],
    summary="部门下拉树",
)
async def treeselect(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(await dept_service.dept_treeselect(db))


@router.get(
    "/{dept_id}", dependencies=[Depends(require_perm("system:dept:query"))], summary="部门详情"
)
async def get_dept(dept_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await dept_service.get_dept(db, dept_id)))


@router.post("", dependencies=[Depends(require_perm("system:dept:add"))], summary="新增部门")
async def create_dept(payload: DeptCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    dept = await dept_service.create_dept(db, payload)
    return success(_dump(dept), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:dept:edit"))], summary="修改部门")
async def update_dept(payload: DeptUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    dept = await dept_service.update_dept(db, payload)
    return success(_dump(dept), msg="修改成功")


@router.delete(
    "/{dept_id}", dependencies=[Depends(require_perm("system:dept:remove"))], summary="删除部门"
)
async def delete_dept(dept_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await dept_service.delete_dept(db, dept_id)
    return success(msg="删除成功")
