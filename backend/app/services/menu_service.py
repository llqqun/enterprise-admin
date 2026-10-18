"""Menu tree to dynamic-route payload.

The shape returned here is a contract with the frontend router: it renders the
sidebar and registers routes from the same array, so both stay consistent by
construction.
"""

import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MenuTypeEnum, StatusEnum
from app.core.deps import CurrentUser
from app.core.exceptions import BusinessException, NotFoundException
from app.models.associations import SysRoleMenu, SysUserRole
from app.models.menu import SysMenu
from app.models.role import SysRole
from app.utils.tree import build_tree

ROUTE_TYPES = (MenuTypeEnum.DIR, MenuTypeEnum.MENU)


def _to_route(menu: SysMenu) -> dict[str, Any]:
    return {
        # A route name must be unique and non-empty for keep-alive to work; fall
        # back to the primary key rather than emitting an empty name.
        "name": menu.route_name or f"Menu{menu.menu_id}",
        "path": menu.path or "",
        "hidden": menu.visible != "0",
        "component": menu.component or None,
        "meta": {"title": menu.menu_name, "icon": menu.icon or None},
    }


async def _visible_menus(db: AsyncSession, user: CurrentUser) -> list[SysMenu]:
    """Every routable menu this user may see, in sibling order."""
    statement = select(SysMenu).where(
        SysMenu.menu_type.in_(ROUTE_TYPES),
        SysMenu.status == StatusEnum.NORMAL,
    )

    if not user.is_admin:
        # Only through the user's own roles. Joined (not subqueried) so MySQL can
        # use the composite primary keys on the two link tables.
        #
        # The role row itself is joined too: `require_perm` and the profile builder
        # both ignore a disabled or deleted role, so skipping it here would let the
        # sidebar advertise menus whose every button answers 403. Two layers giving
        # different answers for the same account is the bug, not the menu itself.
        # `SysRole` carries SoftDeleteMixin, so the global filter adds `del_flag='0'`.
        statement = (
            statement.join(SysRoleMenu, SysRoleMenu.menu_id == SysMenu.menu_id)
            .join(SysUserRole, SysUserRole.role_id == SysRoleMenu.role_id)
            .join(SysRole, SysRole.role_id == SysRoleMenu.role_id)
            .where(
                SysUserRole.user_id == user.user_id,
                SysRole.status == StatusEnum.NORMAL,
            )
        )

    statement = statement.order_by(SysMenu.parent_id, SysMenu.order_num)
    # `.unique()` because the role join can legitimately match the same menu twice.
    return list((await db.scalars(statement)).unique().all())


def _strip_tree_keys(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove the bookkeeping keys used for nesting, recursively."""
    for node in nodes:
        node.pop("id", None)
        node.pop("parent", None)
        _strip_tree_keys(node["children"])
    return nodes


async def get_routers(db: AsyncSession, user: CurrentUser) -> list[dict[str, Any]]:
    """Build the dynamic route tree for a user.

    A user with no menu-bearing roles gets `[]`, which is a successful answer, not
    an error: the frontend then shows an empty sidebar instead of a stack trace.
    """
    menus = await _visible_menus(db, user)
    nodes = [{"id": menu.menu_id, "parent": menu.parent_id, **_to_route(menu)} for menu in menus]
    return _strip_tree_keys(build_tree(nodes, id_field="id", parent_field="parent"))


# ---------------------------------------------------------------------------
# 管理端 CRUD
#
# 与上面的运行时下发分开：`get_routers` 只关心「谁能看到什么」，这里关心「谁能改什么」，
# 两者的查询条件与校验完全不同，混在一起会让两个关注点互相牵制。
# ---------------------------------------------------------------------------

#: 组件路径必须能映射到 `views/` 下的一个文件，前端用 `import.meta.glob` 做映射。
COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_/-]*$")


def _validate_shape(payload: Any) -> None:
    """按节点类型校验：三种节点各自必填什么、禁止什么。"""
    if payload.menu_type == MenuTypeEnum.BUTTON:
        if not (payload.perms or "").strip():
            raise BusinessException("按钮节点必须填写权限标识")
        if payload.component:
            raise BusinessException("按钮节点不能配置组件路径")
        return

    if payload.menu_type == MenuTypeEnum.MENU:
        if not (payload.component or "").strip():
            raise BusinessException("菜单节点必须填写组件路径")
        if not COMPONENT_PATTERN.match(payload.component):
            raise BusinessException("组件路径格式不正确")
        return

    # 目录只渲染一层子菜单，不会挂载组件。
    if payload.component:
        raise BusinessException("目录节点不能配置组件路径")


async def _assert_route_name_free(
    db: AsyncSession, route_name: str | None, *, exclude_id: int | None = None
) -> None:
    """`route_name` 会成为 vue-router 的路由名；重名会静默覆盖另一个页面。

    空值不参与唯一性判断 —— 按钮节点没有路由，有很多个空值是正常的。
    """
    if not (route_name or "").strip():
        return
    statement = select(SysMenu.menu_id).where(SysMenu.route_name == route_name)
    if exclude_id is not None:
        statement = statement.where(SysMenu.menu_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("路由名称已存在")


def _menu_row(menu: SysMenu) -> dict[str, Any]:
    return {
        "menu_id": menu.menu_id,
        "menu_name": menu.menu_name,
        "parent_id": menu.parent_id,
        "order_num": menu.order_num,
        "path": menu.path,
        "component": menu.component,
        "query": menu.query,
        "route_name": menu.route_name,
        "is_frame": menu.is_frame,
        "is_cache": menu.is_cache,
        "menu_type": menu.menu_type,
        "visible": menu.visible,
        "status": menu.status,
        "perms": menu.perms,
        "icon": menu.icon,
    }


async def list_menus(
    db: AsyncSession, *, menu_name: str | None = None, status: str | None = None
) -> tuple[list[dict[str, Any]], int]:
    statement = select(SysMenu).order_by(SysMenu.parent_id, SysMenu.order_num, SysMenu.menu_id)
    if menu_name:
        statement = statement.where(SysMenu.menu_name.contains(menu_name))
    if status:
        statement = statement.where(SysMenu.status == status)

    menus = list(await db.scalars(statement))
    nodes = [{**_menu_row(menu), "id": menu.menu_id, "parent": menu.parent_id} for menu in menus]
    tree = build_tree(nodes, id_field="id", parent_field="parent")
    return _strip_tree_keys(tree), len(nodes)


async def get_menu(db: AsyncSession, menu_id: int) -> SysMenu:
    menu = await db.scalar(select(SysMenu).where(SysMenu.menu_id == menu_id))
    if menu is None:
        raise NotFoundException("菜单不存在")
    return menu


async def create_menu(db: AsyncSession, payload: Any) -> SysMenu:
    _validate_shape(payload)
    await _assert_route_name_free(db, payload.route_name)

    menu = SysMenu(**payload.model_dump())
    db.add(menu)
    await db.flush()
    return menu


async def update_menu(db: AsyncSession, payload: Any) -> SysMenu:
    menu = await get_menu(db, payload.menu_id)
    _validate_shape(payload)
    await _assert_route_name_free(db, payload.route_name, exclude_id=menu.menu_id)

    if payload.parent_id == menu.menu_id:
        raise BusinessException("上级菜单不能是自己")

    for field, value in payload.model_dump(exclude={"menu_id"}).items():
        setattr(menu, field, value)
    await db.flush()
    return menu


async def delete_menu(db: AsyncSession, menu_id: int) -> None:
    """物理删除 —— `sys_menu` 没有 `del_flag`（残留的 perms 比不可逆删除更糟）。"""
    menu = await get_menu(db, menu_id)

    if await db.scalar(select(SysMenu.menu_id).where(SysMenu.parent_id == menu_id).limit(1)):
        raise BusinessException("存在子菜单，不允许删除")

    # 显式清理角色关联。外键是 ON DELETE CASCADE，但依赖数据库隐式行为会让「删菜单会
    # 收回权限」这件事只存在于 DDL 里；这里写明，读代码的人不必去翻迁移文件。
    await db.execute(delete(SysRoleMenu).where(SysRoleMenu.menu_id == menu_id))
    await db.delete(menu)
    await db.flush()


async def menu_treeselect(db: AsyncSession) -> list[dict[str, Any]]:
    menus = list(await db.scalars(select(SysMenu).order_by(SysMenu.parent_id, SysMenu.order_num)))
    nodes = [{"id": menu.menu_id, "parent": menu.parent_id, "label": menu.menu_name} for menu in menus]
    return build_tree(nodes, id_field="id", parent_field="parent")


async def role_menu_treeselect(db: AsyncSession, role_id: int) -> dict[str, Any]:
    """角色授权弹窗要的两样东西：完整菜单树 + 该角色已勾选的菜单 ID。"""
    checked = list(
        await db.scalars(select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role_id))
    )
    return {"menus": await menu_treeselect(db), "checkedKeys": checked}
