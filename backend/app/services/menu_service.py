"""Menu tree to dynamic-route payload.

The shape returned here is a contract with the frontend router: it renders the
sidebar and registers routes from the same array, so both stay consistent by
construction.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MenuTypeEnum, StatusEnum
from app.core.deps import CurrentUser
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
