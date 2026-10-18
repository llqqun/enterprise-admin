"""角色接口。

所有字面量路径（`/authUser/...`、`/changeStatus`、`/dataScope`）都必须声明在 `/{role_id}` 之前。
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.system import (
    AuthUserRequest,
    RoleCreate,
    RoleDataScope,
    RoleOut,
    RoleStatusChange,
    RoleUpdate,
    UserBrief,
)
from app.services import role_service

router = APIRouter(prefix="/role", tags=["system:role"])


def _dump(role: Any) -> dict[str, Any]:
    return RoleOut.model_validate(role).model_dump()


def _dump_users(rows: list[Any]) -> list[dict[str, Any]]:
    return [UserBrief.model_validate(row).model_dump() for row in rows]


def _parse_ids(ids: str) -> list[int]:
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


@router.get("", dependencies=[Depends(require_perm("system:role:list"))], summary="角色列表")
async def list_roles(
    role_name: str | None = None,
    role_key: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await role_service.list_roles(
        db, params, role_name=role_name, role_key=role_key, status=status
    )
    return page([_dump(row) for row in rows], total)


@router.get(
    "/authUser/allocatedList",
    dependencies=[Depends(require_perm("system:role:query"))],
    summary="已分配该角色的用户",
)
async def allocated_users(
    role_id: int, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    rows, total = await role_service.allocated_users(db, params, role_id)
    return page(_dump_users(rows), total)


@router.get(
    "/authUser/unallocatedList",
    dependencies=[Depends(require_perm("system:role:query"))],
    summary="未分配该角色的用户",
)
async def unallocated_users(
    role_id: int, params: PageParams = Depends(), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    rows, total = await role_service.unallocated_users(db, params, role_id)
    return page(_dump_users(rows), total)


@router.put(
    "/authUser/selectAll",
    dependencies=[Depends(require_perm("system:role:edit"))],
    summary="批量授予用户",
)
async def select_all(
    role_id: int, user_ids: str = "", db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    await role_service.grant_users(db, role_id, _parse_ids(user_ids) if user_ids else [])
    return success(msg="授权成功")


@router.put(
    "/authUser/cancel",
    dependencies=[Depends(require_perm("system:role:edit"))],
    summary="取消单个用户授权",
)
async def cancel(
    payload: AuthUserRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    await role_service.revoke_user(db, payload.role_id, payload.user_id)
    return success(msg="取消授权成功")


@router.put(
    "/authUser/cancelAll",
    dependencies=[Depends(require_perm("system:role:edit"))],
    summary="取消该角色的全部用户",
)
async def cancel_all(role_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await role_service.revoke_all(db, role_id)
    return success(msg="取消授权成功")


@router.put(
    "/changeStatus", dependencies=[Depends(require_perm("system:role:edit"))], summary="启用/停用角色"
)
async def change_status(
    payload: RoleStatusChange, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    await role_service.change_status(db, payload.role_id, payload.status)
    return success(msg="修改成功")


@router.put(
    "/dataScope", dependencies=[Depends(require_perm("system:role:edit"))], summary="设置数据范围"
)
async def set_data_scope(
    payload: RoleDataScope, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return success(_dump(await role_service.set_data_scope(db, payload)), msg="修改成功")


@router.get("/{role_id}", dependencies=[Depends(require_perm("system:role:query"))], summary="角色详情")
async def get_role(role_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await role_service.get_role(db, role_id)))


@router.post("", dependencies=[Depends(require_perm("system:role:add"))], summary="新增角色")
async def create_role(payload: RoleCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await role_service.create_role(db, payload)), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:role:edit"))], summary="修改角色")
async def update_role(payload: RoleUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await role_service.update_role(db, payload)), msg="修改成功")


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("system:role:remove"))], summary="删除角色"
)
async def delete_roles(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await role_service.delete_roles(db, _parse_ids(ids))
    return success(msg="删除成功")
