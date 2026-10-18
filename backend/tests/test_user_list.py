"""用户列表与数据权限的真实效果。

这是「数据权限全闭环」的验收点：同一个接口、同一份数据，**不同角色登录后拿到的行数不同**。
断言的是 HTTP 层看到的行数与 `total`，不是 `apply_data_scope` 的内部行为 ——
后者已有 25 条单元测试，这里要证明的是它**真的接在了接口上**。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DataScopeEnum, MenuTypeEnum, StatusEnum
from app.core.security import hash_password
from app.models.associations import SysRoleMenu, SysUserRole
from app.models.dept import SysDept
from app.models.menu import SysMenu
from app.models.role import SysRole
from app.models.user import SysUser

USER_URL = "/api/v1/system/user"
PASSWORD = "Admin@123456"


async def _dept(db: AsyncSession, name: str, parent: SysDept | None = None) -> SysDept:
    dept = SysDept(
        dept_name=name,
        parent_id=0 if parent is None else parent.dept_id,
        ancestors="0" if parent is None else f"{parent.ancestors},{parent.dept_id}",
        order_num=1,
        status=StatusEnum.NORMAL,
    )
    db.add(dept)
    await db.flush()
    return dept


async def _user(db: AsyncSession, name: str, dept: SysDept | None = None) -> SysUser:
    user = SysUser(
        user_name=name,
        nick_name=name,
        password=hash_password(PASSWORD),
        dept_id=None if dept is None else dept.dept_id,
        status=StatusEnum.NORMAL,
    )
    db.add(user)
    await db.flush()
    return user


async def _scoped_user(
    db: AsyncSession, name: str, dept: SysDept, scope: DataScopeEnum
) -> SysUser:
    """A user whose single role grants `system:user:list` and one data scope.

    The permission has to be granted explicitly: a role with no menus grants
    nothing, so without this the endpoint answers 403 and the data-scope assertion
    would never be reached.
    """
    role = SysRole(
        role_name=f"role_{name}",
        role_key=f"role_{name}",
        role_sort=5,
        data_scope=str(int(scope)),
        status=StatusEnum.NORMAL,
    )
    db.add(role)
    await db.flush()

    menu = await db.scalar(select(SysMenu).where(SysMenu.perms == "system:user:list"))
    if menu is None:
        menu = SysMenu(
            menu_name="用户列表",
            parent_id=0,
            order_num=1,
            menu_type=MenuTypeEnum.MENU,
            path="user",
            component="system/user/index",
            route_name="SystemUser",
            perms="system:user:list",
        )
        db.add(menu)
        await db.flush()
    db.add(SysRoleMenu(role_id=role.role_id, menu_id=menu.menu_id))

    user = await _user(db, name, dept)
    db.add(SysUserRole(user_id=user.user_id, role_id=role.role_id))
    await db.flush()
    return user


@pytest.fixture()
async def org(db_session: AsyncSession) -> dict[str, SysUser]:
    """总部 → 研发部 → 前端组，外加市场部。每层至少一个人。"""
    head = await _dept(db_session, "总部")
    dev = await _dept(db_session, "研发部", head)
    frontend = await _dept(db_session, "前端组", dev)
    market = await _dept(db_session, "市场部", head)

    await _user(db_session, "u_head", head)
    await _user(db_session, "u_dev", dev)
    await _user(db_session, "u_frontend", frontend)
    await _user(db_session, "u_market", market)

    return {
        "dept_scoped": await _scoped_user(db_session, "mgr_dev", dev, DataScopeEnum.DEPT_AND_CHILD),
        "self_scoped": await _scoped_user(db_session, "solo", market, DataScopeEnum.SELF),
    }


async def _names(client: AsyncClient, headers: dict[str, str]) -> set[str]:
    resp = await client.get(USER_URL, headers=headers)
    assert resp.status_code == 200, resp.text
    return {row["user_name"] for row in resp.json()["data"]["rows"]}


async def test_admin_sees_everyone(
    client: AsyncClient, admin_headers: dict[str, str], org: dict[str, SysUser]
) -> None:
    names = await _names(client, admin_headers)

    assert {"u_head", "u_dev", "u_frontend", "u_market", "mgr_dev", "solo"} <= names


async def test_a_department_scoped_role_sees_only_its_subtree(
    client: AsyncClient, org: dict[str, SysUser], login
) -> None:
    """`mgr_dev` sits in 研发部 with 本部门及以下, so it must not see 总部 or 市场部."""
    headers = await login("mgr_dev")

    names = await _names(client, headers)

    assert {"u_dev", "u_frontend", "mgr_dev"} <= names
    assert "u_market" not in names
    assert "u_head" not in names


async def test_a_self_scoped_role_sees_only_itself(
    client: AsyncClient, org: dict[str, SysUser], login
) -> None:
    headers = await login("solo")

    assert await _names(client, headers) == {"solo"}


async def test_total_is_scoped_not_global(
    client: AsyncClient, admin_headers: dict[str, str], org: dict[str, SysUser], login
) -> None:
    """A global total with scoped rows would make the UI show phantom pages."""
    as_admin = await client.get(USER_URL, headers=admin_headers, params={"page_size": 1})
    as_self = await client.get(USER_URL, headers=await login("solo"), params={"page_size": 1})

    assert as_admin.json()["data"]["total"] > as_self.json()["data"]["total"] == 1


async def test_row_counts_differ_between_roles(
    client: AsyncClient, org: dict[str, SysUser], login, admin_headers: dict[str, str]
) -> None:
    """The S2 acceptance, as an assertion: same endpoint, different visible rows."""
    admin_rows = len((await client.get(USER_URL, headers=admin_headers)).json()["data"]["rows"])
    manager_rows = len((await client.get(USER_URL, headers=await login("mgr_dev"))).json()["data"]["rows"])
    staff_rows = len((await client.get(USER_URL, headers=await login("solo"))).json()["data"]["rows"])

    assert admin_rows > manager_rows > staff_rows


async def test_a_user_with_no_org_unit_still_sees_itself(
    client: AsyncClient, db_session: AsyncSession, login
) -> None:
    """A dept-scoped rule for a user with no department degrades to 仅本人, not to nothing."""
    await _scoped_user(db_session, "orphan", await _dept(db_session, "空壳部"), DataScopeEnum.DEPT)
    db_session.add(
        SysUser(user_name="outsider", nick_name="外人", password=hash_password(PASSWORD), status=StatusEnum.NORMAL)
    )
    await db_session.flush()

    mobile = await db_session.scalar(select(SysUser).where(SysUser.user_name == "orphan"))
    assert mobile is not None
    mobile.dept_id = None
    await db_session.flush()

    names = await _names(client, await login("orphan"))

    assert names == {"orphan"}


async def test_staff_has_no_permission_to_list_users(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    assert (await client.get(USER_URL, headers=staff_headers)).status_code == 403


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(USER_URL)).status_code == 401
