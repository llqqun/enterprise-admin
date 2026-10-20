"""登录日志查询。

数据本身从 P0 起就在写；这个文件补的是「读」。
刻意没有删除接口 —— 审计日志可被接口抹除，就等于没有审计。
"""

from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_log import SysLoginLog

LOG_URL = "/api/v1/monitor/loginlog"


async def _log(
    db: AsyncSession,
    *,
    user_name: str = "admin",
    status: str = "0",
    when: datetime | None = None,
    msg: str = "登录成功",
    ipaddr: str = "127.0.0.1",
) -> SysLoginLog:
    row = SysLoginLog(
        user_name=user_name,
        ipaddr=ipaddr,
        login_location="内网",
        browser="Chrome",
        os="Windows",
        status=status,
        msg=msg,
        login_time=when or datetime(2026, 10, 20, 10, 0, 0),
    )
    db.add(row)
    await db.flush()
    return row


async def test_list_uses_the_standard_page_envelope(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await _log(db_session)

    resp = await client.get(LOG_URL, headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"rows", "total"}
    assert data["total"] >= 1


async def test_row_carries_the_audit_fields(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await _log(db_session, user_name="audited", ipaddr="10.0.0.9", status="1", msg="用户名或密码错误")

    rows = (await client.get(LOG_URL, headers=admin_headers, params={"user_name": "audited"})).json()[
        "data"
    ]["rows"]

    assert len(rows) == 1
    row = rows[0]
    assert row["ipaddr"] == "10.0.0.9"
    assert row["status"] == "1"
    assert row["msg"] == "用户名或密码错误"
    assert row["browser"] == "Chrome"


async def test_filters_by_user_name(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await _log(db_session, user_name="alice")
    await _log(db_session, user_name="bob")

    rows = (await client.get(LOG_URL, headers=admin_headers, params={"user_name": "ali"})).json()[
        "data"
    ]["rows"]

    assert [row["user_name"] for row in rows] == ["alice"]


async def test_filters_by_status(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """失败行是这套日志存在的理由：锁定与撞库只能靠它们事后发现。"""
    await _log(db_session, user_name="ok_user", status="0")
    await _log(db_session, user_name="bad_user", status="1")

    rows = (await client.get(LOG_URL, headers=admin_headers, params={"status": "1"})).json()["data"][
        "rows"
    ]

    assert [row["user_name"] for row in rows] == ["bad_user"]


async def test_end_date_is_inclusive(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """查 10-20 必须包含 10-20 当天的记录，而不是只到当天零点。"""
    await _log(db_session, user_name="end_day", when=datetime(2026, 10, 20, 23, 59, 0))

    rows = (
        await client.get(
            LOG_URL, headers=admin_headers, params={"begin_date": "2026-10-20", "end_date": "2026-10-20"}
        )
    ).json()["data"]["rows"]

    # 用「包含」而不是「完全相等」：`admin_headers` 这个夹具自己会真实登录一次，
    # 于是库里本来就有一条属于今天的日志，它出现在结果里是正常的。
    assert "end_day" in [row["user_name"] for row in rows]


async def test_date_range_excludes_outside_rows(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await _log(db_session, user_name="inside", when=datetime(2026, 10, 20, 12, 0, 0))
    await _log(db_session, user_name="before", when=datetime(2026, 10, 19, 12, 0, 0))
    await _log(db_session, user_name="after", when=datetime(2026, 10, 21, 12, 0, 0))

    names = [
        row["user_name"]
        for row in (
            await client.get(
                LOG_URL,
                headers=admin_headers,
                params={"begin_date": "2026-10-20", "end_date": "2026-10-20"},
            )
        ).json()["data"]["rows"]
    ]

    assert "inside" in names
    assert "before" not in names
    assert "after" not in names


async def test_malformed_date_is_a_400_not_a_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get(LOG_URL, headers=admin_headers, params={"begin_date": "2026/10/20"})

    assert resp.status_code == 400
    assert "日期" in resp.json()["msg"]


async def test_newest_first(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    base = datetime(2026, 10, 20, 8, 0, 0)
    await _log(db_session, user_name="older", when=base)
    await _log(db_session, user_name="newer", when=base + timedelta(hours=2))

    names = [
        row["user_name"]
        for row in (
            await client.get(LOG_URL, headers=admin_headers, params={"begin_date": "2026-10-20"})
        ).json()["data"]["rows"]
    ]

    # 只断言这两条的相对顺序，不假设它们一定排在最前 —— 夹具自己的登录记录可能更晚。
    assert names.index("newer") < names.index("older")


async def test_a_real_login_writes_a_row(
    client: AsyncClient, admin_headers: dict[str, str], admin_user, login
) -> None:
    """认证流程本身会落日志 —— 这条把「写」与「读」接在一起验证。"""
    before = (await client.get(LOG_URL, headers=admin_headers, params={"user_name": "admin"})).json()[
        "data"
    ]["total"]

    await login("admin")

    after = (await client.get(LOG_URL, headers=admin_headers, params={"user_name": "admin"})).json()[
        "data"
    ]["total"]
    assert after == before + 1


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(LOG_URL)).status_code == 401


async def test_list_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    assert (await client.get(LOG_URL, headers=staff_headers)).status_code == 403
