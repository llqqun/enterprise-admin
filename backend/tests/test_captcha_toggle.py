"""Behaviour that depends on the `CAPTCHA_ENABLED` setting.

Separate file because these tests change configuration rather than exercising the
happy path, and the distinction matters: "the code field is empty" must be a *400
from the captcha service* when captcha is on, and a complete non-issue when it is
off. Getting that wrong is how the login page breaks the moment someone disables
the captcha.
"""

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.user import SysUser

PASSWORD = "Admin@123456"
LOGIN_URL = "/api/v1/auth/login"
CAPTCHA_URL = "/api/v1/auth/captchaImage"


@pytest.fixture()
def captcha_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "CAPTCHA_ENABLED", False)


@pytest.fixture()
def captcha_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "CAPTCHA_ENABLED", True)


async def test_captcha_endpoint_announces_that_it_is_disabled(
    client: AsyncClient, captcha_disabled: None
) -> None:
    resp = await client.get(CAPTCHA_URL)

    assert resp.status_code == 200
    data = resp.json()["data"]
    # A uuid is still returned so the client's request shape never changes.
    assert data["uuid"]
    assert data["captcha_enabled"] is False
    assert data["img"] == ""


async def test_login_accepts_an_empty_code_when_captcha_is_disabled(
    client: AsyncClient, admin_user: SysUser, captcha_disabled: None
) -> None:
    resp = await client.post(
        LOGIN_URL,
        json={"username": "admin", "password": PASSWORD, "code": "", "uuid": ""},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["access_token"]


async def test_login_rejects_an_empty_code_when_captcha_is_enabled(
    client: AsyncClient, admin_user: SysUser, captcha_enabled: None
) -> None:
    """A 400, not a 422: the request is well-formed but the captcha is not satisfied."""
    resp = await client.post(
        LOGIN_URL,
        json={"username": "admin", "password": PASSWORD, "code": "", "uuid": ""},
    )

    assert resp.status_code == 400
    assert resp.json()["msg"] == "验证码已失效，请刷新后重试"


async def test_captcha_endpoint_returns_an_image_when_enabled(
    client: AsyncClient, captcha_enabled: None
) -> None:
    resp = await client.get(CAPTCHA_URL)

    data = resp.json()["data"]
    assert data["captcha_enabled"] is True
    assert data["img"]
