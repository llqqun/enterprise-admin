"""用户写入：唯一性、密码、以及两种「把自己关在门外」的守卫。

密码相关断言一律走**真实登录**（新密码能进、旧密码不能），而不是去比对哈希 ——
后者只能证明字符串变了，证明不了登录会用它。
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ADMIN_ROLE_KEY, StatusEnum
from app.models.associations import SysUserRole
from app.models.role import SysRole
from app.models.user import SysUser

USER_URL = "/api/v1/system/user"
LOGIN_URL = "/api/v1/auth/login"
PASSWORD = "Admin@123456"


async def _create(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    payload = {"user_name": "newbie", "nick_name": "新人", "password": PASSWORD, **fields}
    resp = await client.post(USER_URL, headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _admin_role_id(db_session: AsyncSession) -> int:
    role = await db_session.scalar(select(SysRole).where(SysRole.role_key == ADMIN_ROLE_KEY))
    assert role is not None
    return role.role_id


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


async def test_create_returns_the_user_without_the_password(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _create(client, admin_headers, user_name="alice")

    assert created["user_name"] == "alice"
    assert "password" not in created


async def test_the_new_password_actually_works(
    client: AsyncClient, admin_headers: dict[str, str], login
) -> None:
    """Proves the password was hashed with the real function, not stored as given."""
    await _create(client, admin_headers, user_name="alice")

    headers = await login("alice")

    assert "Authorization" in headers


async def test_duplicate_user_name_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _create(client, admin_headers, user_name="alice")

    resp = await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "alice", "nick_name": "冒名", "password": PASSWORD}
    )

    assert resp.status_code == 400
    assert "已存在" in resp.json()["msg"]


async def test_a_soft_deleted_name_can_be_reused(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """The whole reason `user_name` has no UNIQUE index."""
    created = await _create(client, admin_headers, user_name="alice")
    await client.delete(f"{USER_URL}/{created['user_id']}", headers=admin_headers)

    resp = await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "alice", "nick_name": "重建", "password": PASSWORD}
    )

    assert resp.status_code == 200


async def test_create_assigns_roles(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    role = SysRole(role_name="临时", role_key="tmp_role", role_sort=9, data_scope="5")
    db_session.add(role)
    await db_session.flush()

    created = await _create(client, admin_headers, user_name="alice", role_ids=[role.role_id])

    links = list(
        await db_session.scalars(select(SysUserRole.role_id).where(SysUserRole.user_id == created["user_id"]))
    )
    assert links == [role.role_id]


async def test_create_rejects_an_unknown_role_id(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Otherwise the foreign key turns a bad payload into a 500."""
    resp = await client.post(
        USER_URL,
        headers=admin_headers,
        json={"user_name": "alice", "nick_name": "新人", "password": PASSWORD, "role_ids": [999999]},
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 密码重置
# ---------------------------------------------------------------------------


async def test_reset_password_swaps_the_working_credential(
    client: AsyncClient, admin_headers: dict[str, str], login
) -> None:
    created = await _create(client, admin_headers, user_name="alice")
    await login("alice")  # the old password works

    resp = await client.put(
        f"{USER_URL}/resetPwd",
        headers=admin_headers,
        json={"user_id": created["user_id"], "password": "NewPass@123456"},
    )
    assert resp.status_code == 200

    headers = await login("alice", "NewPass@123456")
    assert "Authorization" in headers

    captcha_uuid = (await client.get("/api/v1/auth/captchaImage")).json()["data"]["uuid"]
    rejected = await client.post(
        LOGIN_URL,
        json={"username": "alice", "password": PASSWORD, "code": "XXXX", "uuid": captcha_uuid},
    )
    assert rejected.status_code == 400


# ---------------------------------------------------------------------------
# 自锁保护
# ---------------------------------------------------------------------------


async def test_cannot_delete_yourself(
    client: AsyncClient, admin_headers: dict[str, str], admin_user: SysUser
) -> None:
    resp = await client.delete(f"{USER_URL}/{admin_user.user_id}", headers=admin_headers)

    assert resp.status_code == 400
    assert "自己" in resp.json()["msg"]


async def test_cannot_disable_yourself(
    client: AsyncClient, admin_headers: dict[str, str], admin_user: SysUser
) -> None:
    resp = await client.put(
        f"{USER_URL}/changeStatus",
        headers=admin_headers,
        json={"user_id": admin_user.user_id, "status": StatusEnum.DISABLED},
    )

    assert resp.status_code == 400
    assert "自己" in resp.json()["msg"]


async def test_deleting_another_admin_is_allowed(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, login
) -> None:
    """The last-superuser guard must not over-block: with two admins, one may go."""
    admin_role_id = await _admin_role_id(db_session)
    await _create(client, admin_headers, user_name="admin2", role_ids=[admin_role_id])
    second = await login("admin2", PASSWORD)

    admin = await db_session.scalar(select(SysUser).where(SysUser.user_name == "admin"))
    assert admin is not None
    resp = await client.delete(f"{USER_URL}/{admin.user_id}", headers=second)

    assert resp.status_code == 200


async def test_list_requires_authentication_and_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    assert (await client.get(USER_URL)).status_code == 401
    assert (
        await client.post(
            USER_URL, headers=staff_headers, json={"user_name": "x", "nick_name": "x", "password": PASSWORD}
        )
    ).status_code == 403
