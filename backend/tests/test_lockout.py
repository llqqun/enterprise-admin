"""Lockout must be keyed on the account, not on the spelling the caller chose.

MySQL compares `user_name` under the `utf8mb4_0900_ai_ci` collation, which is
case-insensitive: `ADMIN` and `admin` resolve to the same row. Keying the failure
counter on the *raw request string* therefore hands an attacker a fresh budget for
every casing, and the documented control ("5 failures locks the account for 10
minutes") holds only for one spelling of the name.

Separate file because these tests are about the counter's key, not about the login
happy path.
"""

from httpx import AsyncClient

from app.core.cache import cache
from app.models.user import SysUser
from app.services.auth_service import CAPTCHA_KEY_PREFIX, LOGIN_FAIL_LIMIT

LOGIN_URL = "/api/v1/auth/login"
CAPTCHA_URL = "/api/v1/auth/captchaImage"
PASSWORD = "Admin@123456"
WRONG = "WrongPass@1"


async def _login(client: AsyncClient, *, username: str, password: str) -> tuple[int, dict]:
    captcha_uuid = (await client.get(CAPTCHA_URL)).json()["data"]["uuid"]
    code = await cache.get(CAPTCHA_KEY_PREFIX + captcha_uuid)
    resp = await client.post(
        LOGIN_URL,
        json={"username": username, "password": password, "code": code, "uuid": captcha_uuid},
    )
    return resp.status_code, resp.json()


async def _exhaust_budget(client: AsyncClient, username: str) -> None:
    for _ in range(LOGIN_FAIL_LIMIT):
        status, _ = await _login(client, username=username, password=WRONG)
        assert status == 400


async def test_lockout_survives_an_uppercase_spelling(
    client: AsyncClient, admin_user: SysUser
) -> None:
    await _exhaust_budget(client, "ADMIN")

    status, body = await _login(client, username="admin", password=PASSWORD)

    assert status == 400
    assert "锁定" in body["msg"]


async def test_lockout_applies_to_an_uppercase_attempt(
    client: AsyncClient, admin_user: SysUser
) -> None:
    await _exhaust_budget(client, "admin")

    status, body = await _login(client, username="ADMIN", password=PASSWORD)

    assert status == 400
    assert "锁定" in body["msg"]


async def test_lockout_survives_a_mixed_case_spelling(
    client: AsyncClient, admin_user: SysUser
) -> None:
    await _exhaust_budget(client, "AdMiN")

    status, body = await _login(client, username="admin", password=PASSWORD)

    assert status == 400
    assert "锁定" in body["msg"]


async def test_lockout_survives_surrounding_whitespace(
    client: AsyncClient, admin_user: SysUser
) -> None:
    """`' admin '` resolves to the same row, so it must share the same budget."""
    await _exhaust_budget(client, "  admin  ")

    status, body = await _login(client, username="admin", password=PASSWORD)

    assert status == 400
    assert "锁定" in body["msg"]


async def test_distinct_accounts_keep_separate_budgets(
    client: AsyncClient, admin_user: SysUser, normal_user: SysUser
) -> None:
    """Normalising the key must not merge two genuinely different accounts."""
    await _exhaust_budget(client, "admin")

    # `staff` keeps its own budget, so the correct password still works.
    status, body = await _login(client, username="staff", password=PASSWORD)

    assert status == 200, body
    assert body["data"]["access_token"]
