"""数据库不可用时的错误语义。

单独重启 / 维护数据库时，客户端应该拿到 **503（稍后重试）**，而不是未解释的 500 ——
否则调用方无法区分「我的请求错了」和「服务暂时取不到数据」。

这两条断言同时钉住了相反的方向：写错的 SQL（`ProgrammingError`）仍然是 500，
不能被这个处理器顺手吞成 503。
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError

from app.db.session import get_db

USER_URL = "/api/v1/system/user"


def _app_of(transport_holder: Any) -> Any:
    """拿到 `client` fixture 内部创建的 app，好往它上面挂 dependency override。

    httpx 没有公开 accessor，读的是 `ASGITransport.app`；拿不到就直接失败，
    免得测试静默地测了个寂寞。
    """
    app = getattr(getattr(transport_holder, "_transport", None), "app", None)
    assert app is not None, "could not reach the ASGI app behind the test client"
    return app


async def test_db_outage_is_503_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    # 先确认正常路径是通的
    assert (await client.get(USER_URL, headers=admin_headers)).status_code == 200

    app = _app_of(client)

    async def _boom():
        raise OperationalError("SELECT 1", {}, Exception("MySQL server has gone away"))
        yield  # pragma: no cover - 生成器永远走不到这里

    app.dependency_overrides[get_db] = _boom
    try:
        response = await client.get(USER_URL, headers=admin_headers)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == 503
    assert "稍后重试" in body["msg"]
    # 不回显底层错误：SQL 与 DSN 都可能出现在里面
    assert "gone away" not in body["msg"]


async def test_interface_error_is_also_503(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """连接被对端关掉（wait_timeout）与连不上一样，都属于「重试就行」。"""
    app = _app_of(client)

    async def _boom():
        raise InterfaceError("cursor closed", {}, Exception("cursor closed"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _boom
    try:
        response = await client.get(USER_URL, headers=admin_headers)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503


async def test_a_broken_query_is_still_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """写错的 SQL 是必须有人修的 bug，不能被当成「数据库暂时不可用」。"""
    app = _app_of(client)

    async def _boom():
        raise ProgrammingError("SELECT * FROM no_such_table", {}, Exception("no such table"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = _boom
    try:
        response = await client.get(USER_URL, headers=admin_headers)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 500
    assert response.json()["code"] == 500


@pytest.mark.parametrize("exc_type", [OperationalError, InterfaceError])
def test_the_two_handled_types_are_registered(exc_type: type[Exception]) -> None:
    """注册是循环做的，这条守着「别把其中一个漏掉」。"""
    from app.main import create_app

    app = create_app()
    assert exc_type in app.exception_handlers or {
        base for base in exc_type.__mro__ if base in app.exception_handlers
    }, f"{exc_type.__name__} has no handler"
