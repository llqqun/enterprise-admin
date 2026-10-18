"""菜单 CRUD。

菜单是唯一**没有 `del_flag`** 的表：删掉必须真的消失，否则它的 `perms` 会残留在所有曾持有它的
角色权限集里。这个反向取舍意味着删除是物理删除，并要确保角色关联一并清理。
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import MenuTypeEnum, StatusEnum
from app.models.associations import SysRoleMenu
from app.models.menu import SysMenu
from app.models.role import SysRole

MENU_URL = "/api/v1/system/menu"


async def _create(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    resp = await client.post(MENU_URL, headers=headers, json=fields)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _directory(client: AsyncClient, headers: dict[str, str], name: str, path: str = "sys") -> dict:
    return await _create(
        client,
        headers,
        parent_id=0,
        menu_name=name,
        menu_type=MenuTypeEnum.DIR,
        path=path,
        order_num=1,
    )


async def _menu(
    client: AsyncClient,
    headers: dict[str, str],
    parent_id: int,
    name: str,
    route_name: str,
    path: str = "list",
    component: str = "system/list/index",
) -> dict:
    return await _create(
        client,
        headers,
        parent_id=parent_id,
        menu_name=name,
        menu_type=MenuTypeEnum.MENU,
        path=path,
        component=component,
        route_name=route_name,
        order_num=1,
    )


async def _button(
    client: AsyncClient, headers: dict[str, str], parent_id: int, name: str, perms: str
) -> dict:
    return await _create(
        client,
        headers,
        parent_id=parent_id,
        menu_name=name,
        menu_type=MenuTypeEnum.BUTTON,
        perms=perms,
        order_num=1,
    )


# ---------------------------------------------------------------------------
# 按类型校验
# ---------------------------------------------------------------------------


async def test_directory_needs_no_component(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    node = await _directory(client, admin_headers, "系统管理")

    assert node["menu_type"] == MenuTypeEnum.DIR
    assert node["component"] is None


async def test_menu_without_component_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.post(
        MENU_URL,
        headers=admin_headers,
        json={
            "parent_id": 0,
            "menu_name": "用户管理",
            "menu_type": MenuTypeEnum.MENU,
            "path": "user",
            "route_name": "SystemUser",
            "order_num": 1,
        },
    )

    assert resp.status_code == 400
    assert "组件" in resp.json()["msg"]


async def test_button_needs_a_permission_code(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """A button node with no `perms` is invisible to the permission system."""
    parent = await _menu(client, admin_headers, 0, "用户管理", "SystemUser")

    resp = await client.post(
        MENU_URL,
        headers=admin_headers,
        json={
            "parent_id": parent["menu_id"],
            "menu_name": "空的按钮",
            "menu_type": MenuTypeEnum.BUTTON,
            "perms": "",
            "order_num": 1,
        },
    )

    assert resp.status_code == 400
    assert "权限" in resp.json()["msg"]


async def test_button_with_a_permission_code_is_accepted(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    parent = await _menu(client, admin_headers, 0, "用户管理", "SystemUser")

    node = await _button(client, admin_headers, parent["menu_id"], "用户新增", "system:user:add")

    assert node["perms"] == "system:user:add"


async def test_directory_may_not_carry_a_component(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """A directory renders a submenu; a component would never be mounted."""
    resp = await client.post(
        MENU_URL,
        headers=admin_headers,
        json={
            "parent_id": 0,
            "menu_name": "系统管理",
            "menu_type": MenuTypeEnum.DIR,
            "path": "system",
            "component": "system/index",
            "order_num": 1,
        },
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 路由名唯一性
# ---------------------------------------------------------------------------


async def test_duplicate_route_name_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """`route_name` becomes a vue-router name; a duplicate silently overwrites."""
    await _menu(client, admin_headers, 0, "用户管理", "SystemUser")

    resp = await client.post(
        MENU_URL,
        headers=admin_headers,
        json={
            "parent_id": 0,
            "menu_name": "另一个用户管理",
            "menu_type": MenuTypeEnum.MENU,
            "path": "user2",
            "component": "system/user/index",
            "route_name": "SystemUser",
            "order_num": 2,
        },
    )

    assert resp.status_code == 400
    assert "路由名称" in resp.json()["msg"]


async def test_many_nodes_may_have_no_route_name(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Buttons have no route, so "unique" must not treat empty as a value."""
    parent = await _menu(client, admin_headers, 0, "用户管理", "SystemUser")

    await _button(client, admin_headers, parent["menu_id"], "新增", "system:user:add")
    await _button(client, admin_headers, parent["menu_id"], "删除", "system:user:remove")


async def test_update_does_not_collide_with_itself(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    node = await _menu(client, admin_headers, 0, "用户管理", "SystemUser")

    resp = await client.put(
        MENU_URL,
        headers=admin_headers,
        json={
            "menu_id": node["menu_id"],
            "parent_id": 0,
            "menu_name": "用户管理",
            "menu_type": MenuTypeEnum.MENU,
            "path": "user",
            "component": "system/user/index",
            "route_name": "SystemUser",
            "order_num": 1,
        },
    )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


async def test_delete_is_refused_while_children_exist(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    parent = await _menu(client, admin_headers, 0, "用户管理", "SystemUser")
    await _button(client, admin_headers, parent["menu_id"], "新增", "system:user:add")

    resp = await client.delete(f"{MENU_URL}/{parent['menu_id']}", headers=admin_headers)

    assert resp.status_code == 400
    assert "子菜单" in resp.json()["msg"] or "下级" in resp.json()["msg"]


async def test_delete_is_physical(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    node = await _directory(client, admin_headers, "临时目录")

    assert (await client.delete(f"{MENU_URL}/{node['menu_id']}", headers=admin_headers)).status_code == 200

    assert await db_session.scalar(select(SysMenu).where(SysMenu.menu_id == node["menu_id"])) is None


async def test_delete_removes_the_role_links(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Otherwise a dangling link could re-grant the code if the id is reused."""
    node = await _directory(client, admin_headers, "临时目录")
    role = SysRole(role_name="临时角色", role_key="tmp_role", role_sort=9, data_scope="1")
    db_session.add(role)
    await db_session.flush()
    db_session.add(SysRoleMenu(role_id=role.role_id, menu_id=node["menu_id"]))
    await db_session.flush()

    await client.delete(f"{MENU_URL}/{node['menu_id']}", headers=admin_headers)

    remaining = list(
        await db_session.scalars(select(SysRoleMenu).where(SysRoleMenu.menu_id == node["menu_id"]))
    )
    assert remaining == []


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


async def test_list_returns_a_tree(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    parent = await _directory(client, admin_headers, "系统管理")
    child = await _menu(client, admin_headers, parent["menu_id"], "用户管理", "SystemUser")

    resp = await client.get(f"{MENU_URL}/list", headers=admin_headers)

    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    top = next(row for row in rows if row["menu_id"] == parent["menu_id"])
    assert [node["menu_id"] for node in top["children"]] == [child["menu_id"]]


async def test_treeselect_shape(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    parent = await _directory(client, admin_headers, "系统管理")

    resp = await client.get(f"{MENU_URL}/treeselect", headers=admin_headers)

    node = next(item for item in resp.json()["data"] if item["id"] == parent["menu_id"])
    assert node["label"] == "系统管理"
    assert node["children"] == []


async def test_role_menu_treeselect_returns_checked_keys(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    node = await _directory(client, admin_headers, "系统管理")
    role = SysRole(role_name="临时角色", role_key="tmp_role2", role_sort=9, data_scope="1")
    db_session.add(role)
    await db_session.flush()
    db_session.add(SysRoleMenu(role_id=role.role_id, menu_id=node["menu_id"]))
    await db_session.flush()

    resp = await client.get(f"{MENU_URL}/roleMenuTreeselect/{role.role_id}", headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert node["menu_id"] in data["checkedKeys"]
    assert any(item["id"] == node["menu_id"] for item in data["menus"])


async def test_get_one_and_404(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    node = await _directory(client, admin_headers, "系统管理")

    assert (await client.get(f"{MENU_URL}/{node['menu_id']}", headers=admin_headers)).json()["data"][
        "menu_name"
    ] == "系统管理"
    assert (await client.get(f"{MENU_URL}/999999", headers=admin_headers)).status_code == 404


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(f"{MENU_URL}/list")).status_code == 401


async def test_write_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(
        MENU_URL,
        headers=staff_headers,
        json={
            "parent_id": 0,
            "menu_name": "偷偷加的菜单",
            "menu_type": MenuTypeEnum.DIR,
            "path": "x",
            "order_num": 1,
        },
    )

    assert resp.status_code == 403
