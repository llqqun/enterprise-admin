"""数据权限：角色 → 行级可见范围。

设计文档 §6.4 要求多角色取**并集**（权限最大化），因此 `DataScope` 承载的是一组规则、
`apply_data_scope` 把它们 OR 起来。这与「取最宽松的那个 mode」**不等价**：一个「本部门」角色
加一个「自定义部门」角色，正确结果是两者都能看，而不是只看自定义的那两个部门。
"""

import dataclasses

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.constants import DataScopeEnum, DelFlagEnum, StatusEnum
from app.core.security import hash_password
from app.models.associations import SysUserRole
from app.models.dept import SysDept
from app.models.role import SysRole
from app.models.user import SysUser
from app.services.auth_service import CAPTCHA_KEY_PREFIX
from app.services.data_scope import (
    DataScope,
    ScopeRule,
    apply_data_scope,
    dept_subtree_ids,
    resolve_data_scope,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _role(mode: DataScopeEnum, *, dept_ids: tuple[int, ...] = (), status: str = StatusEnum.NORMAL) -> SysRole:
    """A transient role — no database needed for the resolution rules."""
    role = SysRole(role_name=f"r{mode}", role_key=f"r{mode}", data_scope=str(int(mode)), status=status)
    if dept_ids:
        role.depts = [SysDept(dept_id=dept_id, dept_name=f"d{dept_id}", parent_id=0, ancestors="0") for dept_id in dept_ids]
    return role


async def _make_dept(
    db: AsyncSession, name: str, parent: SysDept | None = None, *, deleted: bool = False
) -> SysDept:
    dept = SysDept(
        dept_name=name,
        parent_id=0 if parent is None else parent.dept_id,
        ancestors="0" if parent is None else f"{parent.ancestors},{parent.dept_id}",
        order_num=1,
        status=StatusEnum.NORMAL,
        del_flag=DelFlagEnum.DELETED if deleted else DelFlagEnum.EXISTS,
    )
    db.add(dept)
    await db.flush()
    return dept


async def _make_user(db: AsyncSession, name: str, dept: SysDept) -> SysUser:
    user = SysUser(user_name=name, nick_name=name, password="x", dept_id=dept.dept_id, status=StatusEnum.NORMAL)
    db.add(user)
    await db.flush()
    return user


# ---------------------------------------------------------------------------
# resolve_data_scope — pure
# ---------------------------------------------------------------------------


def test_admin_is_unrestricted() -> None:
    scope = resolve_data_scope([_role(DataScopeEnum.SELF)], user_id=1, dept_id=10, is_admin=True)

    assert scope.unrestricted is True


def test_single_role_becomes_one_rule() -> None:
    scope = resolve_data_scope([_role(DataScopeEnum.DEPT)], user_id=7, dept_id=10, is_admin=False)

    assert scope.rules == (ScopeRule(mode=int(DataScopeEnum.DEPT), dept_id=10),)
    assert scope.unrestricted is False


def test_an_all_role_makes_the_whole_scope_unrestricted() -> None:
    """One unrestricted role must not be narrowed by a narrower one."""
    scope = resolve_data_scope(
        [_role(DataScopeEnum.SELF), _role(DataScopeEnum.ALL)], user_id=7, dept_id=10, is_admin=False
    )

    assert scope.unrestricted is True


def test_roles_union_rather_than_pick_one() -> None:
    """DEPT + CUSTOM must keep both, not drop the department one."""
    scope = resolve_data_scope(
        [_role(DataScopeEnum.DEPT), _role(DataScopeEnum.CUSTOM, dept_ids=(5, 6))],
        user_id=7,
        dept_id=10,
        is_admin=False,
    )

    assert ScopeRule(mode=int(DataScopeEnum.DEPT), dept_id=10) in scope.rules
    assert ScopeRule(
        mode=int(DataScopeEnum.CUSTOM), custom_dept_ids=frozenset({5, 6})
    ) in scope.rules
    assert len(scope.rules) == 2


def test_custom_roles_union_their_dept_sets() -> None:
    scope = resolve_data_scope(
        [_role(DataScopeEnum.CUSTOM, dept_ids=(5,)), _role(DataScopeEnum.CUSTOM, dept_ids=(6, 7))],
        user_id=7,
        dept_id=10,
        is_admin=False,
    )

    assert scope.rules == (
        ScopeRule(mode=int(DataScopeEnum.CUSTOM), custom_dept_ids=frozenset({5, 6, 7})),
    )


def test_scope_without_a_department_falls_back_to_self() -> None:
    """A dept-scoped rule for a user who has no department would otherwise see nothing."""
    scope = resolve_data_scope([_role(DataScopeEnum.DEPT)], user_id=7, dept_id=None, is_admin=False)

    assert scope.rules == (ScopeRule(mode=int(DataScopeEnum.SELF)),)


def test_disabled_roles_are_ignored() -> None:
    """Same rule as the menu layer: a revoked role grants nothing."""
    scope = resolve_data_scope(
        [_role(DataScopeEnum.ALL, status=StatusEnum.DISABLED)], user_id=7, dept_id=10, is_admin=False
    )

    assert scope.rules == ()


def test_no_roles_means_no_rows() -> None:
    scope = resolve_data_scope([], user_id=7, dept_id=10, is_admin=False)

    assert scope.rules == ()
    assert scope.unrestricted is False


def test_self_rule_targets_the_user() -> None:
    scope = resolve_data_scope([_role(DataScopeEnum.SELF)], user_id=7, dept_id=10, is_admin=False)

    assert scope.user_id == 7
    assert scope.rules == (ScopeRule(mode=int(DataScopeEnum.SELF)),)


# ---------------------------------------------------------------------------
# dept_subtree_ids — recursive CTE
# ---------------------------------------------------------------------------


async def test_dept_subtree_includes_descendants(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    mid = await _make_dept(db_session, "研发部", root)
    leaf = await _make_dept(db_session, "前端组", mid)

    subtree = await dept_subtree_ids(db_session, root.dept_id)

    assert subtree == {root.dept_id, mid.dept_id, leaf.dept_id}


async def test_dept_subtree_of_a_leaf_is_itself(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    mid = await _make_dept(db_session, "研发部", root)
    leaf = await _make_dept(db_session, "前端组", mid)

    assert await dept_subtree_ids(db_session, leaf.dept_id) == {leaf.dept_id}


async def test_dept_subtree_excludes_siblings_and_ancestors(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    left = await _make_dept(db_session, "研发部", root)
    right = await _make_dept(db_session, "市场部", root)

    subtree = await dept_subtree_ids(db_session, left.dept_id)

    assert right.dept_id not in subtree
    assert root.dept_id not in subtree


async def test_dept_subtree_ignores_a_soft_deleted_branch(db_session: AsyncSession) -> None:
    """A deleted department must disappear from every subtree it sat in."""
    root = await _make_dept(db_session, "总部")
    gone = await _make_dept(db_session, "已撤销部门", root, deleted=True)
    orphan = await _make_dept(db_session, "挂在其下的组", gone)

    subtree = await dept_subtree_ids(db_session, root.dept_id)

    # `gone` is filtered by the global soft-delete listener, so the recursion stops
    # there and `orphan` is unreachable — which is the honest answer for a branch
    # that no longer exists.
    assert gone.dept_id not in subtree
    assert orphan.dept_id not in subtree


# ---------------------------------------------------------------------------
# apply_data_scope — on a real query
# ---------------------------------------------------------------------------


async def _user_names(db: AsyncSession, statement) -> set[str]:
    result = await db.scalars(statement)
    return {user.user_name for user in result.all()}


async def test_unrestricted_scope_does_not_filter(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    other = await _make_dept(db_session, "市场部", root)
    await _make_user(db_session, "u_root", root)
    await _make_user(db_session, "u_other", other)

    scope = resolve_data_scope([_role(DataScopeEnum.ALL)], user_id=1, dept_id=root.dept_id, is_admin=False)
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"u_root", "u_other"}


async def test_dept_scope_sees_only_its_own_department(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    child = await _make_dept(db_session, "研发部", root)
    await _make_user(db_session, "u_root", root)
    await _make_user(db_session, "u_child", child)

    scope = resolve_data_scope([_role(DataScopeEnum.DEPT)], user_id=1, dept_id=child.dept_id, is_admin=False)
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"u_child"}


async def test_dept_and_child_scope_sees_the_subtree(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    mid = await _make_dept(db_session, "研发部", root)
    leaf = await _make_dept(db_session, "前端组", mid)
    sibling = await _make_dept(db_session, "市场部", root)
    await _make_user(db_session, "u_mid", mid)
    await _make_user(db_session, "u_leaf", leaf)
    await _make_user(db_session, "u_sibling", sibling)

    scope = resolve_data_scope(
        [_role(DataScopeEnum.DEPT_AND_CHILD)], user_id=1, dept_id=mid.dept_id, is_admin=False
    )
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"u_mid", "u_leaf"}


async def test_self_scope_sees_only_the_user(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    me = await _make_user(db_session, "me", root)
    await _make_user(db_session, "colleague", root)

    scope = resolve_data_scope([_role(DataScopeEnum.SELF)], user_id=me.user_id, dept_id=root.dept_id, is_admin=False)
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"me"}


async def test_custom_scope_sees_only_the_listed_departments(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    picked = await _make_dept(db_session, "市场部", root)
    ignored = await _make_dept(db_session, "财务部", root)
    await _make_user(db_session, "u_picked", picked)
    await _make_user(db_session, "u_ignored", ignored)

    scope = resolve_data_scope(
        [_role(DataScopeEnum.CUSTOM, dept_ids=(picked.dept_id,))],
        user_id=1,
        dept_id=root.dept_id,
        is_admin=False,
    )
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"u_picked"}


async def test_a_narrower_role_does_not_narrow_a_broader_one(db_session: AsyncSession) -> None:
    """The union rule, proved end to end: DEPT ∪ CUSTOM sees both sets."""
    root = await _make_dept(db_session, "总部")
    mine = await _make_dept(db_session, "研发部", root)
    picked = await _make_dept(db_session, "市场部", root)
    ignored = await _make_dept(db_session, "财务部", root)
    await _make_user(db_session, "u_mine", mine)
    await _make_user(db_session, "u_picked", picked)
    await _make_user(db_session, "u_ignored", ignored)

    scope = resolve_data_scope(
        [_role(DataScopeEnum.DEPT), _role(DataScopeEnum.CUSTOM, dept_ids=(picked.dept_id,))],
        user_id=1,
        dept_id=mine.dept_id,
        is_admin=False,
    )
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"u_mine", "u_picked"}


async def test_a_scope_with_no_rules_sees_nothing(db_session: AsyncSession) -> None:
    """Fail closed: a user whose roles grant no scope must not see every row."""
    root = await _make_dept(db_session, "总部")
    await _make_user(db_session, "u_root", root)

    scope = resolve_data_scope([], user_id=1, dept_id=root.dept_id, is_admin=False)
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == set()


async def test_admin_scope_bypasses_everything(db_session: AsyncSession) -> None:
    root = await _make_dept(db_session, "总部")
    other = await _make_dept(db_session, "市场部", root)
    await _make_user(db_session, "u_root", root)
    await _make_user(db_session, "u_other", other)

    scope = resolve_data_scope([_role(DataScopeEnum.SELF)], user_id=1, dept_id=None, is_admin=True)
    statement = await apply_data_scope(db_session, select(SysUser), SysUser, scope)

    assert await _user_names(db_session, statement) == {"u_root", "u_other"}


def test_data_scope_is_frozen() -> None:
    """It is built once per request and shared; mutating it would be a race."""
    scope = DataScope(user_id=1, is_admin=False, rules=(ScopeRule(mode=int(DataScopeEnum.SELF)),))

    with pytest.raises(dataclasses.FrozenInstanceError):
        scope.user_id = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 接线：解析出来的范围必须真的挂到当前用户上
# ---------------------------------------------------------------------------

SCOPE_URL = "/__test__/scope"
LOGIN_URL = "/api/v1/auth/login"
CAPTCHA_URL = "/api/v1/auth/captchaImage"
PASSWORD = "Admin@123456"


async def _auth_headers(client: AsyncClient, username: str) -> dict[str, str]:
    captcha_uuid = (await client.get(CAPTCHA_URL)).json()["data"]["uuid"]
    code = await cache.get(CAPTCHA_KEY_PREFIX + captcha_uuid)
    resp = await client.post(
        LOGIN_URL,
        json={"username": username, "password": PASSWORD, "code": code, "uuid": captcha_uuid},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


@pytest.fixture()
async def department_manager(db_session: AsyncSession) -> SysUser:
    """A user whose only role is scoped to their own department and below."""
    dept = await _make_dept(db_session, "研发部")
    role = SysRole(
        role_name="部门主管",
        role_key="dept_manager_scope",
        role_sort=2,
        data_scope=str(int(DataScopeEnum.DEPT_AND_CHILD)),
        status=StatusEnum.NORMAL,
    )
    db_session.add(role)
    await db_session.flush()

    user = SysUser(
        user_name="scoped_manager",
        nick_name="部门主管",
        password=hash_password(PASSWORD),
        dept_id=dept.dept_id,
        status=StatusEnum.NORMAL,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(SysUserRole(user_id=user.user_id, role_id=role.role_id))
    await db_session.flush()
    return user


@pytest.fixture()
async def roleless_user(db_session: AsyncSession) -> SysUser:
    user = SysUser(
        user_name="roleless",
        nick_name="无角色",
        password=hash_password(PASSWORD),
        status=StatusEnum.NORMAL,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def test_scope_is_wired_for_a_department_manager(
    client: AsyncClient, department_manager: SysUser
) -> None:
    headers = await _auth_headers(client, "scoped_manager")

    resp = await client.get(SCOPE_URL, headers=headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["rules"] == [
        {"mode": int(DataScopeEnum.DEPT_AND_CHILD), "dept_id": department_manager.dept_id, "custom_dept_ids": []}
    ]
    assert data["unrestricted"] is False


async def test_scope_is_unrestricted_for_an_admin(
    client: AsyncClient, admin_user: SysUser
) -> None:
    headers = await _auth_headers(client, "admin")

    data = (await client.get(SCOPE_URL, headers=headers)).json()["data"]

    assert data["unrestricted"] is True
    assert data["rules"] == []


async def test_scope_grants_nothing_for_a_user_without_roles(
    client: AsyncClient, roleless_user: SysUser
) -> None:
    """Fail closed: an account with no roles must not default to "sees everything"."""
    headers = await _auth_headers(client, "roleless")

    data = (await client.get(SCOPE_URL, headers=headers)).json()["data"]

    assert data["unrestricted"] is False
    assert data["grants_nothing"] is True
