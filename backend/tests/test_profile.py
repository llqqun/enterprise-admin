"""改自己的资料与密码。

最要紧的一条是**字段白名单**：`PUT /auth/profile` 只接受昵称/邮箱/手机/性别。
如果它顺便接受 `dept_id`、`status` 或角色，那么每个登录用户都拿到了一个提权入口 ——
把自己挪进别的部门会扩大数据权限，把 `status` 改成 0 能自己启用一个被停用的账号。
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import SysUser

PROFILE_URL = "/api/v1/auth/profile"
PASSWORD_URL = "/api/v1/auth/password"
PASSWORD = "Admin@123456"


async def test_update_own_profile(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    resp = await client.put(
        PROFILE_URL,
        headers=admin_headers,
        json={"nick_name": "改过的昵称", "email": "me@example.com", "phonenumber": "13800000000", "sex": "1"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["nick_name"] == "改过的昵称"
    assert data["email"] == "me@example.com"
    assert "password" not in data


async def test_profile_update_cannot_touch_privileged_fields(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, admin_user: SysUser
) -> None:
    """多发几个字段不会报错，但**一个都不该生效**。"""
    resp = await client.put(
        PROFILE_URL,
        headers=admin_headers,
        json={
            "nick_name": "还是我",
            "user_name": "hacker",
            "status": "1",
            "dept_id": 99,
            "role_ids": [1],
        },
    )
    assert resp.status_code == 200

    await db_session.refresh(admin_user)
    assert admin_user.user_name == "admin", "用户名不能被自助接口改掉"
    assert admin_user.status == "0", "状态不能被自助接口改掉"
    assert admin_user.dept_id != 99, "部门不能被自助接口改掉"


async def test_password_change_requires_the_old_password(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """不校验原密码的话，一个被劫持的会话就能把账号锁成自己的。"""
    resp = await client.put(
        PASSWORD_URL,
        headers=admin_headers,
        json={"old_password": "WrongOld@1", "new_password": "BrandNew@123"},
    )

    assert resp.status_code == 400
    assert "原密码" in resp.json()["msg"]


async def test_password_change_swaps_the_working_credential(
    client: AsyncClient, admin_headers: dict[str, str], admin_user: SysUser, login
) -> None:
    resp = await client.put(
        PASSWORD_URL,
        headers=admin_headers,
        json={"old_password": PASSWORD, "new_password": "BrandNew@123"},
    )
    assert resp.status_code == 200

    # 新密码能登录；旧密码不能
    assert "Authorization" in await login("admin", "BrandNew@123")

    captcha_uuid = (await client.get("/api/v1/auth/captchaImage")).json()["data"]["uuid"]
    rejected = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": PASSWORD, "code": "XXXX", "uuid": captcha_uuid},
    )
    assert rejected.status_code == 400


async def test_password_change_rejects_the_same_password(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.put(
        PASSWORD_URL,
        headers=admin_headers,
        json={"old_password": PASSWORD, "new_password": PASSWORD},
    )

    assert resp.status_code == 400
    assert "相同" in resp.json()["msg"]


async def test_password_change_revokes_other_sessions_only(
    client: AsyncClient, admin_user: SysUser, login
) -> None:
    """改密码最常见的动机是「旧密码可能泄露」——那时把别人留在登录态里等于白改。"""
    first = await login("admin")  # 另一个会话
    second = await login("admin")  # 当前用来改密码的会话

    resp = await client.put(
        PASSWORD_URL,
        headers=second,
        json={"old_password": PASSWORD, "new_password": "AfterChange@123"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked_sessions"] >= 1

    # 另一个会话被踢下线
    assert (await client.get("/api/v1/auth/profile", headers=first)).status_code == 401
    # 当前会话仍然有效
    assert (await client.get("/api/v1/auth/profile", headers=second)).status_code == 200


async def test_new_password_must_meet_the_length_rule(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.put(
        PASSWORD_URL,
        headers=admin_headers,
        json={"old_password": PASSWORD, "new_password": "123"},
    )

    assert resp.status_code == 422


async def test_new_password_must_fit_bcrypt(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """bcrypt 只吃 72 字节，超长在 schema 层就拒，不要留到哈希层变成 500。"""
    resp = await client.put(
        PASSWORD_URL,
        headers=admin_headers,
        json={"old_password": PASSWORD, "new_password": "a" * 100},
    )

    assert resp.status_code == 422


async def test_profile_requires_authentication(client: AsyncClient) -> None:
    assert (
        await client.put(PROFILE_URL, json={"nick_name": "x"})
    ).status_code == 401


async def test_password_requires_authentication(client: AsyncClient) -> None:
    assert (
        await client.put(PASSWORD_URL, json={"old_password": "a", "new_password": "bbbbbb"})
    ).status_code == 401
