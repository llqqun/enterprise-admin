"""Menu tree building and dynamic route delivery."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import WILDCARD_PERM
from app.core.deps import CurrentUser
from app.models.associations import SysRoleMenu, SysUserRole
from app.models.menu import SysMenu
from app.models.role import SysRole
from app.models.user import SysUser
from app.services.menu_service import get_routers
from app.utils.tree import build_tree

ROUTERS_URL = "/api/v1/auth/routers"


def _admin() -> CurrentUser:
    return CurrentUser(
        user_id=1, user_name="admin", dept_id=None, is_admin=True, perms={WILDCARD_PERM}
    )


def _non_admin(user_id: int = 999) -> CurrentUser:
    return CurrentUser(
        user_id=user_id, user_name="ghost", dept_id=None, is_admin=False, perms=set()
    )


# ---------------------------------------------------------------------------
# build_tree
# ---------------------------------------------------------------------------


def test_build_tree_nests_children() -> None:
    nodes = [
        {"id": 1, "parent": 0, "name": "root"},
        {"id": 2, "parent": 1, "name": "child"},
        {"id": 3, "parent": 2, "name": "grandchild"},
    ]

    tree = build_tree(nodes, id_field="id", parent_field="parent")

    assert len(tree) == 1
    assert tree[0]["name"] == "root"
    assert tree[0]["children"][0]["name"] == "child"
    assert tree[0]["children"][0]["children"][0]["name"] == "grandchild"


def test_build_tree_handles_multiple_roots() -> None:
    nodes = [
        {"id": 1, "parent": 0, "name": "a"},
        {"id": 2, "parent": 0, "name": "b"},
    ]

    tree = build_tree(nodes, id_field="id", parent_field="parent")

    assert [node["name"] for node in tree] == ["a", "b"]


def test_build_tree_promotes_orphans_to_roots() -> None:
    """A node whose parent is missing must not vanish silently."""
    nodes = [
        {"id": 1, "parent": 0, "name": "root"},
        {"id": 2, "parent": 4242, "name": "orphan"},
    ]

    tree = build_tree(nodes, id_field="id", parent_field="parent")

    assert {node["name"] for node in tree} == {"root", "orphan"}


def test_build_tree_respects_a_custom_children_field() -> None:
    nodes = [
        {"id": 1, "parent": 0, "name": "root"},
        {"id": 2, "parent": 1, "name": "child"},
    ]

    tree = build_tree(nodes, id_field="id", parent_field="parent", children_field="routes")

    assert tree[0]["routes"][0]["name"] == "child"
    assert "children" not in tree[0]


def test_build_tree_of_nothing_is_empty() -> None:
    assert build_tree([], id_field="id", parent_field="parent") == []


# ---------------------------------------------------------------------------
# get_routers
# ---------------------------------------------------------------------------


async def test_routers_for_admin_is_not_empty(
    db_session: AsyncSession, menu_tree: dict[str, SysMenu]
) -> None:
    routers = await get_routers(db_session, _admin())

    assert {node["path"] for node in routers} == {"/system", "/monitor"}


async def test_routers_excludes_button_nodes(
    db_session: AsyncSession, menu_tree: dict[str, SysMenu]
) -> None:
    """A button carries a permission code but is not a page; it must not route."""
    routers = await get_routers(db_session, _admin())

    paths = str(routers)
    assert "用户新增" not in paths
    system = next(node for node in routers if node["path"] == "/system")
    assert [child["path"] for child in system["children"]] == ["user"]


async def test_routers_excludes_disabled_menus(
    db_session: AsyncSession, menu_tree: dict[str, SysMenu]
) -> None:
    routers = await get_routers(db_session, _admin())

    assert "/disabled" not in {node["path"] for node in routers}


async def test_routers_node_shape(
    db_session: AsyncSession, menu_tree: dict[str, SysMenu]
) -> None:
    """The frontend renders straight from this shape, so it is a contract."""
    routers = await get_routers(db_session, _admin())

    system = next(node for node in routers if node["path"] == "/system")
    assert set(system) >= {"name", "path", "hidden", "component", "meta", "children"}
    assert system["meta"]["title"] == "系统管理"
    assert isinstance(system["hidden"], bool)
    assert system["component"] is None

    user_page = system["children"][0]
    assert user_page["component"] == "system/user/index"
    assert user_page["name"] == "SystemUser"
    assert user_page["children"] == []


async def test_routers_for_a_role_without_menus_is_an_empty_list(
    db_session: AsyncSession,
) -> None:
    """Review Focus #5: the empty case is a successful empty answer, not an error."""
    routers = await get_routers(db_session, _non_admin())

    assert routers == []


async def test_routers_are_scoped_to_the_users_roles(
    db_session: AsyncSession, menu_tree: dict[str, SysMenu]
) -> None:
    """A non-admin sees only what their own roles grant."""
    role = SysRole(
        role_name="监控只读", role_key="monitor_reader", role_sort=3, data_scope="5", status="0"
    )
    db_session.add(role)
    await db_session.flush()

    for menu_key in ("monitor", "online"):
        db_session.add(
            SysRoleMenu(role_id=role.role_id, menu_id=menu_tree[menu_key].menu_id)
        )
    await db_session.flush()

    user = SysUser(user_name="monitor_user", nick_name="m", password="x", status="0")
    db_session.add(user)
    await db_session.flush()
    db_session.add(SysUserRole(user_id=user.user_id, role_id=role.role_id))
    await db_session.flush()

    routers = await get_routers(db_session, _non_admin(user.user_id))

    assert {node["path"] for node in routers} == {"/monitor"}


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


async def test_routers_endpoint_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get(ROUTERS_URL)

    assert resp.status_code == 401
