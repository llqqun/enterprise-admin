"""菜单接口。

`/list`、`/treeselect`、`/roleMenuTreeselect/{role_id}` 都必须声明在 `/{menu_id}` 之前。
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import page, success
from app.db.session import get_db
from app.schemas.system import MenuCreate, MenuOut, MenuUpdate
from app.services import menu_service

router = APIRouter(prefix="/menu", tags=["system:menu"])


def _dump(menu: Any) -> dict[str, Any]:
    return MenuOut.model_validate(menu).model_dump()


@router.get("/list", dependencies=[Depends(require_perm("system:menu:list"))], summary="菜单列表（树）")
async def list_menus(
    menu_name: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await menu_service.list_menus(db, menu_name=menu_name, status=status)
    return page(rows, total)


@router.get(
    "/treeselect", dependencies=[Depends(require_perm("system:menu:list"))], summary="菜单下拉树"
)
async def treeselect(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(await menu_service.menu_treeselect(db))


@router.get(
    "/roleMenuTreeselect/{role_id}",
    dependencies=[Depends(require_perm("system:menu:list"))],
    summary="角色已授权的菜单树",
)
async def role_menu_treeselect(role_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(await menu_service.role_menu_treeselect(db, role_id))


@router.get(
    "/{menu_id}", dependencies=[Depends(require_perm("system:menu:query"))], summary="菜单详情"
)
async def get_menu(menu_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await menu_service.get_menu(db, menu_id)))


@router.post("", dependencies=[Depends(require_perm("system:menu:add"))], summary="新增菜单")
async def create_menu(payload: MenuCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await menu_service.create_menu(db, payload)), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:menu:edit"))], summary="修改菜单")
async def update_menu(payload: MenuUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(_dump(await menu_service.update_menu(db, payload)), msg="修改成功")


@router.delete(
    "/{menu_id}", dependencies=[Depends(require_perm("system:menu:remove"))], summary="删除菜单"
)
async def delete_menu(menu_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await menu_service.delete_menu(db, menu_id)
    return success(msg="删除成功")
