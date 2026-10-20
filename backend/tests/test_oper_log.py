"""操作日志：装饰器写入与查询。

两个必须钉死的点：
1. **请求参数里的密码不能进日志** —— 否则一条审计日志就成了明文凭据库。
2. **记录失败不能影响业务** —— 审计重要，但不值得用「记不上就 500」去换。
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oper_log import SysOperLog
from app.services.oper_log_service import MASK, _sanitize

OPERLOG_URL = "/api/v1/monitor/operlog"
USER_URL = "/api/v1/system/user"
PASSWORD = "Secret@12345"


# ---------------------------------------------------------------------------
# 脱敏（纯函数）
# ---------------------------------------------------------------------------


def test_sanitize_masks_top_level_password() -> None:
    assert _sanitize({"user_name": "alice", "password": "x"})["password"] == MASK


def test_sanitize_masks_nested_and_camel_case_keys() -> None:
    """嵌套与 `newPassword` 这类写法都要覆盖 —— 只处理第一层等于没处理。"""
    cleaned = _sanitize({"user": {"name": "a", "newPassword": "x"}, "list": [{"pwd": "y"}]})

    assert cleaned["user"]["newPassword"] == MASK
    assert cleaned["list"][0]["pwd"] == MASK
    assert cleaned["user"]["name"] == "a"


def test_sanitize_keeps_ordinary_fields() -> None:
    cleaned = _sanitize({"post_code": "dev", "status": "0", "count": 3})

    assert cleaned == {"post_code": "dev", "status": "0", "count": 3}


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------


async def test_a_decorated_write_records_a_row(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    resp = await client.post(
        USER_URL,
        headers=admin_headers,
        json={"user_name": "logged_user", "nick_name": "被记录", "password": PASSWORD},
    )
    assert resp.status_code == 200

    row = await db_session.scalar(
        select(SysOperLog).where(SysOperLog.title == "用户管理").order_by(SysOperLog.oper_id.desc())
    )
    assert row is not None
    assert row.request_method == "POST"
    assert row.oper_url == "/api/v1/system/user"
    assert row.oper_name == "admin"
    assert row.status == "0"
    assert row.cost_ms >= 0


async def test_the_password_never_reaches_the_log(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """这条是整套日志里最要紧的断言。"""
    await client.post(
        USER_URL,
        headers=admin_headers,
        json={"user_name": "masked_user", "nick_name": "脱敏", "password": PASSWORD},
    )

    row = await db_session.scalar(
        select(SysOperLog).where(SysOperLog.oper_url == "/api/v1/system/user").order_by(SysOperLog.oper_id.desc())
    )
    assert row is not None and row.oper_param is not None
    assert PASSWORD not in row.oper_param
    assert MASK in row.oper_param
    # 其余字段仍然可读 —— 脱敏的是密码，不是整条日志
    assert "masked_user" in row.oper_param


async def test_a_failed_operation_is_recorded_as_an_error(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """失败行是这套日志的价值所在：只记成功的日志回答不了「谁尝试了什么」。"""
    await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "dup", "nick_name": "a", "password": PASSWORD}
    )
    before = int(await db_session.scalar(select(func.count()).select_from(SysOperLog)) or 0)

    resp = await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "dup", "nick_name": "b", "password": PASSWORD}
    )
    assert resp.status_code == 400

    rows = list(
        await db_session.scalars(
            select(SysOperLog).where(SysOperLog.status == "1").order_by(SysOperLog.oper_id.desc())
        )
    )
    assert rows, "failed operation should have been recorded"
    assert rows[0].error_msg is not None and "已存在" in rows[0].error_msg
    assert int(await db_session.scalar(select(func.count()).select_from(SysOperLog)) or 0) == before + 1


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


async def test_list_uses_the_standard_page_envelope(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "for_list", "nick_name": "x", "password": PASSWORD}
    )

    resp = await client.get(OPERLOG_URL, headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"rows", "total"}
    assert data["total"] >= 1


async def test_list_filters_by_title_and_status(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "f1", "nick_name": "x", "password": PASSWORD}
    )

    ok = await client.get(OPERLOG_URL, headers=admin_headers, params={"title": "用户", "status": "0"})
    none = await client.get(OPERLOG_URL, headers=admin_headers, params={"title": "不存在的模块"})

    assert ok.json()["data"]["total"] >= 1
    assert none.json()["data"]["total"] == 0


async def test_list_filters_by_operator(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "f2", "nick_name": "x", "password": PASSWORD}
    )

    mine = await client.get(OPERLOG_URL, headers=admin_headers, params={"oper_name": "admin"})
    other = await client.get(OPERLOG_URL, headers=admin_headers, params={"oper_name": "nobody"})

    assert mine.json()["data"]["total"] >= 1
    assert other.json()["data"]["total"] == 0


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(OPERLOG_URL)).status_code == 401


async def test_list_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    assert (await client.get(OPERLOG_URL, headers=staff_headers)).status_code == 403


# ---------------------------------------------------------------------------
# 删除与清空
# ---------------------------------------------------------------------------


async def test_delete_writes_its_own_audit_row(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """删日志这件事本身也要留痕 —— 否则「谁清掉了审计」永远查不出来。"""
    await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "to_purge", "nick_name": "x", "password": PASSWORD}
    )
    target = await db_session.scalar(
        select(SysOperLog).where(SysOperLog.oper_url == "/api/v1/system/user").order_by(SysOperLog.oper_id.desc())
    )
    assert target is not None

    resp = await client.delete(f"{OPERLOG_URL}/{target.oper_id}", headers=admin_headers)

    assert resp.status_code == 200
    remaining = await db_session.scalar(select(SysOperLog).where(SysOperLog.oper_id == target.oper_id))
    assert remaining is None
    marker = await db_session.scalar(
        select(SysOperLog).where(SysOperLog.method == "delete_oper_logs").order_by(SysOperLog.oper_id.desc())
    )
    assert marker is not None and marker.oper_name == "admin"


async def test_clean_empties_the_table_but_leaves_a_marker(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post(
        USER_URL, headers=admin_headers, json={"user_name": "to_clean", "nick_name": "x", "password": PASSWORD}
    )

    resp = await client.delete(f"{OPERLOG_URL}/clean", headers=admin_headers)

    assert resp.status_code == 200
    rows = list(await db_session.scalars(select(SysOperLog)))
    assert len(rows) == 1
    assert rows[0].method == "clean_oper_logs"
    assert rows[0].oper_name == "admin"


async def test_delete_requires_its_own_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    """`monitor:operlog:remove` 与 `:list` 是两个权限码：能看日志不等于能删日志。"""
    assert (await client.delete(f"{OPERLOG_URL}/1", headers=staff_headers)).status_code == 403


async def test_malformed_id_list_is_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    assert (await client.delete(f"{OPERLOG_URL}/1,abc", headers=admin_headers)).status_code == 422
