"""Authorization: token validation, logout, refresh rotation, permission checks.

Kept apart from `test_auth.py` on purpose: that file proves *who you are*, this one
proves *what you may do*.
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.constants import DelFlagEnum, StatusEnum
from app.models.token import SysUserToken
from app.models.user import SysUser
from app.services.auth_service import CAPTCHA_KEY_PREFIX

LOGIN_URL = "/api/v1/auth/login"
CAPTCHA_URL = "/api/v1/auth/captchaImage"
PROFILE_URL = "/api/v1/auth/profile"
LOGOUT_URL = "/api/v1/auth/logout"
REFRESH_URL = "/api/v1/auth/refresh"
PROTECTED_URL = "/__test__/need-perm"
PASSWORD = "Admin@123456"

TOKEN_REJECTED_MSG = "登录状态已失效，请重新登录"


async def _login_tokens(client: AsyncClient, username: str = "admin") -> dict:
    captcha_uuid = (await client.get(CAPTCHA_URL)).json()["data"]["uuid"]
    code = await cache.get(CAPTCHA_KEY_PREFIX + captcha_uuid)
    resp = await client.post(
        LOGIN_URL,
        json={"username": username, "password": PASSWORD, "code": code, "uuid": captcha_uuid},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------


async def test_profile_requires_a_token(client: AsyncClient) -> None:
    resp = await client.get(PROFILE_URL)

    assert resp.status_code == 401


async def test_profile_rejects_garbage_token(client: AsyncClient) -> None:
    resp = await client.get(PROFILE_URL, headers=_bearer("not.a.jwt"))

    assert resp.status_code == 401
    assert resp.json()["msg"] == TOKEN_REJECTED_MSG


async def test_profile_rejects_malformed_authorization_header(client: AsyncClient) -> None:
    resp = await client.get(PROFILE_URL, headers={"Authorization": "Bearer"})

    assert resp.status_code == 401


async def test_profile_rejects_a_token_signed_for_another_user(
    client: AsyncClient, admin_user: SysUser
) -> None:
    """A token whose jti was never persisted must not authenticate anyone."""
    from app.core.security import create_token
    from datetime import timedelta

    forged, _ = create_token(admin_user.user_id, "access", timedelta(minutes=30))

    resp = await client.get(PROFILE_URL, headers=_bearer(forged))

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


async def test_profile_returns_user_roles_and_permissions(
    client: AsyncClient, admin_user: SysUser
) -> None:
    tokens = await _login_tokens(client)

    resp = await client.get(PROFILE_URL, headers=_bearer(tokens["access_token"]))

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["user"]["user_name"] == "admin"
    assert data["roles"] == ["admin"]
    # The superuser carries a wildcard rather than an exhaustive list, so a newly
    # added permission cannot lock the administrator out of their own system.
    assert data["permissions"] == ["*:*:*"]


async def test_profile_never_returns_password(client: AsyncClient, admin_user: SysUser) -> None:
    tokens = await _login_tokens(client)

    resp = await client.get(PROFILE_URL, headers=_bearer(tokens["access_token"]))

    assert "password" not in resp.text
    assert "$2b$" not in resp.text


async def test_profile_permissions_follow_the_role(
    client: AsyncClient, permitted_user: SysUser
) -> None:
    tokens = await _login_tokens(client, username="limited")

    resp = await client.get(PROFILE_URL, headers=_bearer(tokens["access_token"]))

    data = resp.json()["data"]
    assert data["roles"] == ["limited"]
    assert data["permissions"] == ["system:test:view"]


async def test_profile_of_a_permissionless_user_is_not_an_error(
    client: AsyncClient, normal_user: SysUser
) -> None:
    """Review Focus #5: empty permissions must be an empty list, not a failure."""
    tokens = await _login_tokens(client, username="staff")

    resp = await client.get(PROFILE_URL, headers=_bearer(tokens["access_token"]))

    assert resp.status_code == 200
    assert resp.json()["data"]["permissions"] == []
    assert resp.json()["data"]["roles"] == ["staff"]


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def test_logout_requires_a_token(client: AsyncClient) -> None:
    resp = await client.post(LOGOUT_URL)

    assert resp.status_code == 401


async def test_logout_invalidates_the_token_immediately(
    client: AsyncClient, admin_user: SysUser
) -> None:
    tokens = await _login_tokens(client)
    headers = _bearer(tokens["access_token"])
    assert (await client.get(PROFILE_URL, headers=headers)).status_code == 200

    assert (await client.post(LOGOUT_URL, headers=headers)).status_code == 200

    resp = await client.get(PROFILE_URL, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["msg"] == TOKEN_REJECTED_MSG


async def test_logout_also_ends_the_refresh_session(
    client: AsyncClient, admin_user: SysUser
) -> None:
    tokens = await _login_tokens(client)

    await client.post(LOGOUT_URL, headers=_bearer(tokens["access_token"]))

    resp = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


async def test_logout_marks_the_row_revoked(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    tokens = await _login_tokens(client)

    await client.post(LOGOUT_URL, headers=_bearer(tokens["access_token"]))

    row = await db_session.scalar(select(SysUserToken))
    assert row is not None
    assert row.revoked is True


# ---------------------------------------------------------------------------
# Refresh rotation (Review Focus #3)
# ---------------------------------------------------------------------------


async def test_refresh_returns_a_new_pair(client: AsyncClient, admin_user: SysUser) -> None:
    tokens = await _login_tokens(client)

    resp = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"] != tokens["access_token"]
    assert data["refresh_token"] != tokens["refresh_token"]


async def test_refresh_rotates_and_rejects_the_old_refresh_token(
    client: AsyncClient, admin_user: SysUser
) -> None:
    """Replaying a rotated refresh token must fail — that is the whole point."""
    tokens = await _login_tokens(client)
    first = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200

    replay = await client.post(REFRESH_URL, json={"refresh_token": tokens["refresh_token"]})

    assert replay.status_code == 401


async def test_access_token_cannot_be_used_as_a_refresh_token(
    client: AsyncClient, admin_user: SysUser
) -> None:
    tokens = await _login_tokens(client)

    resp = await client.post(REFRESH_URL, json={"refresh_token": tokens["access_token"]})

    assert resp.status_code == 401


async def test_refresh_token_cannot_be_used_as_an_access_token(
    client: AsyncClient, admin_user: SysUser
) -> None:
    tokens = await _login_tokens(client)

    resp = await client.get(PROFILE_URL, headers=_bearer(tokens["refresh_token"]))

    assert resp.status_code == 401


async def test_refresh_rejects_garbage(client: AsyncClient, admin_user: SysUser) -> None:
    resp = await client.post(REFRESH_URL, json={"refresh_token": "not.a.jwt"})

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------


async def test_admin_bypasses_the_permission_check(
    client: AsyncClient, admin_user: SysUser
) -> None:
    tokens = await _login_tokens(client)

    resp = await client.get(PROTECTED_URL, headers=_bearer(tokens["access_token"]))

    assert resp.status_code == 200


async def test_non_admin_without_the_permission_gets_403(
    client: AsyncClient, normal_user: SysUser
) -> None:
    tokens = await _login_tokens(client, username="staff")

    resp = await client.get(PROTECTED_URL, headers=_bearer(tokens["access_token"]))

    assert resp.status_code == 403
    assert resp.json()["code"] == 403


async def test_non_admin_with_the_permission_passes(
    client: AsyncClient, permitted_user: SysUser
) -> None:
    tokens = await _login_tokens(client, username="limited")

    resp = await client.get(PROTECTED_URL, headers=_bearer(tokens["access_token"]))

    assert resp.status_code == 200


async def test_permission_check_requires_authentication_first(client: AsyncClient) -> None:
    resp = await client.get(PROTECTED_URL)

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Revocation follows the account, not just the token
# ---------------------------------------------------------------------------


async def test_disabling_an_account_invalidates_its_live_token(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    tokens = await _login_tokens(client)
    headers = _bearer(tokens["access_token"])

    user = await db_session.scalar(select(SysUser).where(SysUser.user_name == "admin"))
    assert user is not None
    user.status = StatusEnum.DISABLED
    await db_session.flush()

    resp = await client.get(PROFILE_URL, headers=headers)
    assert resp.status_code == 401


async def test_deleting_an_account_invalidates_its_live_token(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    tokens = await _login_tokens(client)
    headers = _bearer(tokens["access_token"])

    user = await db_session.scalar(select(SysUser).where(SysUser.user_name == "admin"))
    assert user is not None
    user.del_flag = DelFlagEnum.DELETED
    await db_session.flush()

    resp = await client.get(PROFILE_URL, headers=headers)
    assert resp.status_code == 401
