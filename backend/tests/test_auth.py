"""Login chain: captcha, credential check, lockout, token persistence, audit log."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.constants import DelFlagEnum, StatusEnum
from app.core.security import hash_password, verify_password
from app.models.login_log import SysLoginLog
from app.models.token import SysUserToken
from app.models.user import SysUser
from app.services.auth_service import (
    CAPTCHA_KEY_PREFIX,
    LOGIN_FAIL_LIMIT,
    LOGIN_FAIL_KEY_PREFIX,
)

LOGIN_URL = "/api/v1/auth/login"
CAPTCHA_URL = "/api/v1/auth/captchaImage"
PASSWORD = "Admin@123456"


async def _issued_captcha(client: AsyncClient) -> tuple[str, str]:
    """Mint a captcha and read its answer out of the cache.

    Reading the cache is the only way to know the code without breaking the captcha
    on purpose; an endpoint that reveals it would be a worse trade.
    """
    resp = await client.get(CAPTCHA_URL)
    assert resp.status_code == 200
    data = resp.json()["data"]
    code = await cache.get(CAPTCHA_KEY_PREFIX + data["uuid"])
    assert code, "captcha answer was not stored"
    return data["uuid"], code


async def _login(
    client: AsyncClient,
    *,
    username: str = "admin",
    password: str = PASSWORD,
    code: str | None = None,
    uuid: str | None = None,
) -> tuple[int, dict]:
    """Post a login. Omitted captcha parts are filled in deliberately:

    * neither given  -> a real, freshly minted captcha (the happy path)
    * code only      -> a valid code with an unknown uuid (expired/invented session)
    * uuid only      -> a real session with a deliberately wrong code
    """
    if uuid is None and code is None:
        uuid, code = await _issued_captcha(client)
    if uuid is None:
        uuid = "0" * 32
    if code is None:
        code = "XXXX"

    resp = await client.post(
        LOGIN_URL,
        json={"username": username, "password": password, "code": code, "uuid": uuid},
    )
    return resp.status_code, resp.json()


# ---------------------------------------------------------------------------
# Captcha
# ---------------------------------------------------------------------------


async def test_captcha_endpoint_returns_uuid_and_png(client: AsyncClient) -> None:
    resp = await client.get(CAPTCHA_URL)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["uuid"]) == 32
    assert data["captcha_enabled"] is True
    assert data["img"]


async def test_captcha_endpoint_issues_a_distinct_uuid_each_time(client: AsyncClient) -> None:
    first = (await client.get(CAPTCHA_URL)).json()["data"]["uuid"]
    second = (await client.get(CAPTCHA_URL)).json()["data"]["uuid"]

    assert first != second


async def test_captcha_is_single_use(client: AsyncClient, admin_user: SysUser) -> None:
    uuid, code = await _issued_captcha(client)

    status, _ = await _login(client, code=code, uuid=uuid)
    assert status == 200

    # Same uuid and code a second time: the answer was consumed on first use.
    status, body = await _login(client, code=code, uuid=uuid)
    assert status == 400
    assert body["msg"] == "验证码已失效，请刷新后重试"


async def test_login_rejects_unknown_captcha_uuid(client: AsyncClient, admin_user: SysUser) -> None:
    status, body = await _login(client, code="ABCD", uuid="0" * 32)

    assert status == 400
    assert body["msg"] == "验证码已失效，请刷新后重试"


async def test_login_rejects_wrong_captcha(client: AsyncClient, admin_user: SysUser) -> None:
    uuid, code = await _issued_captcha(client)
    wrong = "AAAA" if code != "AAAA" else "BBBB"

    status, body = await _login(client, code=wrong, uuid=uuid)

    assert status == 400
    assert body["msg"] == "验证码已失效，请刷新后重试"


async def test_captcha_check_is_case_insensitive(client: AsyncClient, admin_user: SysUser) -> None:
    uuid, code = await _issued_captcha(client)

    status, _ = await _login(client, code=code.lower(), uuid=uuid)

    assert status == 200


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


async def test_login_success_returns_two_tokens(client: AsyncClient, admin_user: SysUser) -> None:
    status, body = await _login(client)

    assert status == 200
    data = body["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["access_token"] != data["refresh_token"]


async def test_login_response_does_not_leak_password_hash(
    client: AsyncClient, admin_user: SysUser
) -> None:
    uuid, code = await _issued_captcha(client)

    resp = await client.post(
        LOGIN_URL,
        json={"username": "admin", "password": PASSWORD, "code": code, "uuid": uuid},
    )

    assert resp.status_code == 200
    raw = resp.text
    assert "$2b$" not in raw
    assert PASSWORD not in raw


async def test_unknown_user_and_wrong_password_are_indistinguishable(
    client: AsyncClient, admin_user: SysUser
) -> None:
    _, wrong_password = await _login(client, password="WrongPass@1")
    _, unknown_user = await _login(client, username="ghost", password="WrongPass@1")

    assert wrong_password["code"] == unknown_user["code"] == 400
    assert wrong_password["msg"] == unknown_user["msg"] == "用户名或密码错误"


async def test_disabled_account_is_rejected(client: AsyncClient, disabled_user: SysUser) -> None:
    status, body = await _login(client, username="disabled")

    assert status == 400
    assert body["msg"] == "账号已停用，请联系管理员"


async def test_soft_deleted_account_cannot_log_in(
    client: AsyncClient, deleted_admin_user: SysUser
) -> None:
    """A logically deleted account must be invisible, not merely forbidden."""
    status, body = await _login(client)

    assert status == 400
    assert body["msg"] == "用户名或密码错误"


async def test_over_long_password_is_a_validation_error(
    client: AsyncClient, admin_user: SysUser
) -> None:
    """Guards the 72-byte bcrypt limit: a 422, never a 500."""
    status, body = await _login(client, password="a" * 200)

    assert status == 422
    assert body["code"] == 422


# ---------------------------------------------------------------------------
# Lockout
# ---------------------------------------------------------------------------


async def test_login_locks_after_five_failures(client: AsyncClient, admin_user: SysUser) -> None:
    for _ in range(LOGIN_FAIL_LIMIT):
        status, _ = await _login(client, password="WrongPass@1")
        assert status == 400

    status, body = await _login(client, password="WrongPass@1")

    assert status == 400
    assert "锁定" in body["msg"]


async def test_locked_account_rejects_the_correct_password_too(
    client: AsyncClient, admin_user: SysUser
) -> None:
    for _ in range(LOGIN_FAIL_LIMIT):
        await _login(client, password="WrongPass@1")

    status, _ = await _login(client)

    assert status == 400


async def test_successful_login_resets_failure_counter(
    client: AsyncClient, admin_user: SysUser
) -> None:
    for _ in range(LOGIN_FAIL_LIMIT - 1):
        await _login(client, password="WrongPass@1")

    status, _ = await _login(client)
    assert status == 200

    counter = await cache.get(LOGIN_FAIL_KEY_PREFIX + "admin")
    assert not counter


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


async def test_login_creates_user_token_row(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    _, body = await _login(client)

    rows = (await db_session.scalars(select(SysUserToken))).all()

    assert len(rows) == 1
    assert rows[0].user_id == admin_user.user_id
    assert body["data"]["access_token"]
    assert rows[0].revoked is False


async def test_token_expiry_is_after_the_login_moment(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    await _login(client)

    row = await db_session.scalar(select(SysUserToken))

    assert row is not None
    assert row.access_expire > row.login_time
    assert row.refresh_expire > row.access_expire


async def test_login_writes_success_log(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    await _login(client)

    log = await db_session.scalar(select(SysLoginLog))

    assert log is not None
    assert log.user_name == "admin"
    assert log.status == "0"


async def test_failed_login_writes_failure_log(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    await _login(client, password="WrongPass@1")

    log = await db_session.scalar(select(SysLoginLog))

    assert log is not None
    assert log.status == "1"
    assert log.msg == "用户名或密码错误"


async def test_login_updates_last_login_metadata(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    await _login(client)

    user = await db_session.scalar(select(SysUser).where(SysUser.user_id == admin_user.user_id))

    assert user is not None
    assert user.login_date is not None
    assert user.login_ip


async def test_failed_login_does_not_create_a_token(
    client: AsyncClient, admin_user: SysUser, db_session: AsyncSession
) -> None:
    await _login(client, password="WrongPass@1")

    count = await db_session.scalar(select(func.count()).select_from(SysUserToken))

    assert count == 0


async def test_stored_password_is_a_bcrypt_hash(admin_user: SysUser) -> None:
    """Guards the fixture itself: the seeded credential must not be plaintext."""
    assert admin_user.password != PASSWORD
    assert verify_password(PASSWORD, admin_user.password) is True


async def test_captcha_failure_does_not_increment_lockout_counter(
    client: AsyncClient, admin_user: SysUser
) -> None:
    """Otherwise anyone could lock a known account without knowing its password."""
    for _ in range(LOGIN_FAIL_LIMIT + 2):
        await _login(client, code="XXXX")

    counter = await cache.get(LOGIN_FAIL_KEY_PREFIX + "admin")
    assert not counter


@pytest.mark.parametrize("username", ["", " ", "admin' OR '1'='1"])
async def test_malformed_usernames_are_rejected_cleanly(
    client: AsyncClient, admin_user: SysUser, username: str
) -> None:
    """Empty input is a 422; a misspelled or hostile one is a 400. Never a 500."""
    status, body = await _login(client, username=username, password="WrongPass@1")

    assert status in (400, 422)
    assert body["code"] == status
    assert "Traceback" not in str(body)


def test_seed_constants_are_sane() -> None:
    assert LOGIN_FAIL_LIMIT == 5
    assert DelFlagEnum.DELETED == "2"
    assert StatusEnum.DISABLED == "1"
    assert hash_password("x") != "x"
