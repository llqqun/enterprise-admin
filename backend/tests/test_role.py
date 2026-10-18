"""角色 CRUD、菜单授权与数据范围。

本任务里最危险的两件事：**自锁**（删掉或停用 `admin` 角色后没人能再进后台）与
**数据范围设置不生效**（写了 `sys_role_dept` 但 `data_scope` 没变）。两者都单独钉了测试。
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ADMIN_ROLE_KEY, DataScopeEnum, StatusEnum
from app.models.associations import SysRoleDept, SysRoleMenu, SysUserRole
from app.models.dept import SysDept
from app.models.role import SysRole
from app.models.user import SysUser

ROLE_URL = "/api/v1/system/role"
ROUTERS_URL = "/api/v1/auth/routers"


async def _create(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    payload = {"role_name": "测试角色", "role_key": "test_role", "role_sort": 5, **fields}
    resp = await client.post(ROLE_URL, headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _role_with_menu(
    client: AsyncClient, headers: dict[str, str], db_session: AsyncSession, menu_id: int, **fields: object
) -> dict:
    role = await _create(client, headers, **fields)
    db_session.add(SysRoleMenu(role_id=role["role_id"], menu_id=menu_id))
    await db_session.flush()
    return role


# ---------------------------------------------------------------------------
# 基本 CRUD
# ---------------------------------------------------------------------------


async def test_create_then_get(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _create(client, admin_headers, role_name="运维", role_key="ops")

    resp = await client.get(f"{ROLE_URL}/{created['role_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["role_key"] == "ops"
    assert resp.json()["data"]["data_scope"] == str(int(DataScopeEnum.ALL))


async def test_get_unknown_is_404(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    assert (await client.get(f"{ROLE_URL}/999999", headers=admin_headers)).status_code == 404


async def test_list_is_paged(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _create(client, admin_headers, role_key="a")
    await _create(client, admin_headers, role_key="b")

    resp = await client.get(ROLE_URL, headers=admin_headers, params={"page_num": 1, "page_size": 1})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 3  # two created plus the seeded admin role
    assert len(data["rows"]) == 1


async def test_list_filters_by_name_and_key(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _create(client, admin_headers, role_name="运维", role_key="ops")
    await _create(client, admin_headers, role_name="访客", role_key="guest")

    by_name = await client.get(ROLE_URL, headers=admin_headers, params={"role_name": "运维"})
    by_key = await client.get(ROLE_URL, headers=admin_headers, params={"role_key": "guest"})

    assert [row["role_key"] for row in by_name.json()["data"]["rows"]] == ["ops"]
    assert [row["role_name"] for row in by_key.json()["data"]["rows"]] == ["访客"]


async def test_update_changes_fields(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _create(client, admin_headers, role_key="ops")

    resp = await client.put(
        ROLE_URL,
        headers=admin_headers,
        json={
            "role_id": created["role_id"],
            "role_name": "运维组",
            "role_key": "ops",
            "role_sort": 9,
            "status": StatusEnum.NORMAL,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["role_name"] == "运维组"


async def test_duplicate_role_key_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _create(client, admin_headers, role_key="ops")

    resp = await client.post(
        ROLE_URL, headers=admin_headers, json={"role_name": "另一个", "role_key": "ops", "role_sort": 1}
    )

    assert resp.status_code == 400
    assert "已存在" in resp.json()["msg"]


async def test_a_soft_deleted_role_key_can_be_reused(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _create(client, admin_headers, role_key="ops")
    await client.delete(f"{ROLE_URL}/{created['role_id']}", headers=admin_headers)

    resp = await client.post(
        ROLE_URL, headers=admin_headers, json={"role_name": "重建", "role_key": "ops", "role_sort": 1}
    )

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 自锁保护
# ---------------------------------------------------------------------------


async def test_the_admin_role_cannot_be_deleted(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Deleting the superuser role locks everyone out of the system permanently."""
    admin_role = await db_session.scalar(select(SysRole).where(SysRole.role_key == ADMIN_ROLE_KEY))
    assert admin_role is not None

    resp = await client.delete(f"{ROLE_URL}/{admin_role.role_id}", headers=admin_headers)

    assert resp.status_code == 400
    assert "超级管理员" in resp.json()["msg"] or "内置" in resp.json()["msg"]


async def test_the_admin_role_cannot_be_disabled(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    admin_role = await db_session.scalar(select(SysRole).where(SysRole.role_key == ADMIN_ROLE_KEY))
    assert admin_role is not None

    resp = await client.put(
        f"{ROLE_URL}/changeStatus",
        headers=admin_headers,
        json={"role_id": admin_role.role_id, "status": StatusEnum.DISABLED},
    )

    assert resp.status_code == 400


async def test_the_admin_role_key_cannot_be_renamed(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Renaming the key would silently revoke the wildcard permission."""
    admin_role = await db_session.scalar(select(SysRole).where(SysRole.role_key == ADMIN_ROLE_KEY))
    assert admin_role is not None

    resp = await client.put(
        ROLE_URL,
        headers=admin_headers,
        json={
            "role_id": admin_role.role_id,
            "role_name": "超级管理员",
            "role_key": "not_admin",
            "role_sort": 1,
            "status": StatusEnum.NORMAL,
        },
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 停用即时生效（Review Focus #5）
# ---------------------------------------------------------------------------


async def test_disabling_a_role_immediately_removes_its_menus(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    login,
    menu_tree,
    normal_user: SysUser,
) -> None:
    """A disabled role must stop granting menus on the very next request."""
    role = await _role_with_menu(
        client, admin_headers, db_session, menu_tree["system"].menu_id, role_key="temp_manager"
    )
    db_session.add(SysUserRole(user_id=normal_user.user_id, role_id=role["role_id"]))
    await db_session.flush()

    headers = await login(normal_user.user_name)
    before = await client.get(ROUTERS_URL, headers=headers)
    assert any(node["path"] == "/system" for node in before.json()["data"])

    disabled = await client.put(
        f"{ROLE_URL}/changeStatus",
        headers=admin_headers,
        json={"role_id": role["role_id"], "status": StatusEnum.DISABLED},
    )
    assert disabled.status_code == 200

    after = await client.get(ROUTERS_URL, headers=headers)
    assert after.json()["data"] == []


# ---------------------------------------------------------------------------
# 数据范围
# ---------------------------------------------------------------------------


async def test_setting_a_custom_data_scope_writes_the_departments(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    role = await _create(client, admin_headers, role_key="scoped")
    first = await db_session.scalar(select(SysRole).where(SysRole.role_id == role["role_id"]))
    assert first is not None
    # Real departments: `sys_role_dept.dept_id` is a foreign key, so inventing ids
    # would prove only that the database rejects them.
    departments = [
        SysDept(dept_name="研发部", parent_id=0, ancestors="0", order_num=1),
        SysDept(dept_name="市场部", parent_id=0, ancestors="0", order_num=2),
    ]
    db_session.add_all(departments)
    await db_session.flush()
    dept_ids = [dept.dept_id for dept in departments]

    resp = await client.put(
        f"{ROLE_URL}/dataScope",
        headers=admin_headers,
        json={"role_id": role["role_id"], "data_scope": str(int(DataScopeEnum.CUSTOM)), "dept_ids": dept_ids},
    )

    assert resp.status_code == 200
    links = list(
        await db_session.scalars(
            select(SysRoleDept.dept_id).where(SysRoleDept.role_id == role["role_id"])
        )
    )
    assert sorted(links) == sorted(dept_ids)
    await db_session.refresh(first)
    assert first.data_scope == str(int(DataScopeEnum.CUSTOM))


async def test_data_scope_rejects_an_unknown_department_id(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """A bad dept id must be a 400, not a foreign-key 500."""
    role = await _create(client, admin_headers, role_key="scoped")

    resp = await client.put(
        f"{ROLE_URL}/dataScope",
        headers=admin_headers,
        json={"role_id": role["role_id"], "data_scope": str(int(DataScopeEnum.CUSTOM)), "dept_ids": [999999]},
    )

    assert resp.status_code == 400
    assert "部门" in resp.json()["msg"]


async def test_setting_a_non_custom_scope_clears_the_departments(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Otherwise stale links would silently widen the scope if it is switched back."""
    role = await _create(client, admin_headers, role_key="scoped")
    dept = SysDept(dept_name="研发部", parent_id=0, ancestors="0", order_num=1)
    db_session.add(dept)
    await db_session.flush()
    db_session.add(SysRoleDept(role_id=role["role_id"], dept_id=dept.dept_id))
    await db_session.flush()

    resp = await client.put(
        f"{ROLE_URL}/dataScope",
        headers=admin_headers,
        json={"role_id": role["role_id"], "data_scope": str(int(DataScopeEnum.SELF)), "dept_ids": [dept.dept_id]},
    )

    assert resp.status_code == 200
    links = list(
        await db_session.scalars(select(SysRoleDept.dept_id).where(SysRoleDept.role_id == role["role_id"]))
    )
    assert links == []


async def test_data_scope_rejects_an_unknown_mode(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    role = await _create(client, admin_headers, role_key="scoped")

    resp = await client.put(
        f"{ROLE_URL}/dataScope",
        headers=admin_headers,
        json={"role_id": role["role_id"], "data_scope": "9", "dept_ids": []},
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 删除清理
# ---------------------------------------------------------------------------


async def test_delete_removes_every_link(
    client: AsyncClient,
    admin_headers: dict[str, str],
    db_session: AsyncSession,
    menu_tree,
    normal_user: SysUser,
) -> None:
    role = await _create(client, admin_headers, role_key="doomed")
    dept = SysDept(dept_name="研发部", parent_id=0, ancestors="0", order_num=1)
    db_session.add(dept)
    await db_session.flush()
    db_session.add(SysRoleMenu(role_id=role["role_id"], menu_id=menu_tree["system"].menu_id))
    db_session.add(SysRoleDept(role_id=role["role_id"], dept_id=dept.dept_id))
    db_session.add(SysUserRole(user_id=normal_user.user_id, role_id=role["role_id"]))
    await db_session.flush()

    resp = await client.delete(f"{ROLE_URL}/{role['role_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert list(await db_session.scalars(select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role["role_id"]))) == []
    assert list(await db_session.scalars(select(SysRoleDept.dept_id).where(SysRoleDept.role_id == role["role_id"]))) == []
    assert list(await db_session.scalars(select(SysUserRole.user_id).where(SysUserRole.role_id == role["role_id"]))) == []


async def test_batch_delete(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    first = await _create(client, admin_headers, role_key="a")
    second = await _create(client, admin_headers, role_key="b")

    resp = await client.delete(f"{ROLE_URL}/{first['role_id']},{second['role_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert (await client.get(f"{ROLE_URL}/{first['role_id']}", headers=admin_headers)).status_code == 404


# ---------------------------------------------------------------------------
# 用户授权
# ---------------------------------------------------------------------------


async def test_allocated_and_unallocated_lists(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, normal_user: SysUser
) -> None:
    role = await _create(client, admin_headers, role_key="granted")
    db_session.add(SysUserRole(user_id=normal_user.user_id, role_id=role["role_id"]))
    await db_session.flush()

    allocated = await client.get(
        f"{ROLE_URL}/authUser/allocatedList", headers=admin_headers, params={"role_id": role["role_id"]}
    )
    unallocated = await client.get(
        f"{ROLE_URL}/authUser/unallocatedList", headers=admin_headers, params={"role_id": role["role_id"]}
    )

    assert [row["user_id"] for row in allocated.json()["data"]["rows"]] == [normal_user.user_id]
    assert normal_user.user_id not in [row["user_id"] for row in unallocated.json()["data"]["rows"]]


async def test_cancel_removes_the_grant(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, normal_user: SysUser
) -> None:
    role = await _create(client, admin_headers, role_key="granted")
    db_session.add(SysUserRole(user_id=normal_user.user_id, role_id=role["role_id"]))
    await db_session.flush()

    resp = await client.put(
        f"{ROLE_URL}/authUser/cancel",
        headers=admin_headers,
        json={"role_id": role["role_id"], "user_id": normal_user.user_id},
    )

    assert resp.status_code == 200
    assert list(await db_session.scalars(select(SysUserRole.user_id).where(SysUserRole.role_id == role["role_id"]))) == []


async def test_select_all_grants_every_listed_user(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, normal_user: SysUser
) -> None:
    role = await _create(client, admin_headers, role_key="granted")

    resp = await client.put(
        f"{ROLE_URL}/authUser/selectAll",
        headers=admin_headers,
        params={"role_id": role["role_id"], "user_ids": str(normal_user.user_id)},
    )

    assert resp.status_code == 200
    assert sorted(
        await db_session.scalars(select(SysUserRole.user_id).where(SysUserRole.role_id == role["role_id"]))
    ) == [normal_user.user_id]


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(ROLE_URL)).status_code == 401


async def test_write_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(
        ROLE_URL, headers=staff_headers, json={"role_name": "偷偷建的", "role_key": "x", "role_sort": 1}
    )

    assert resp.status_code == 403
