"""在线用户：活动会话列表与强制下线。

「在线」的判据是 refresh 令牌未过期且未撤销 —— 用 access 令牌判断会把一个仍在用系统的人
显示成离线（access 只有 30 分钟）。
"""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import SysUserToken
from app.models.user import SysUser
from app.utils.timeutil import utcnow

ONLINE_URL = "/api/v1/monitor/online"
PASSWORD = "Admin@123456"


async def _sessions(db: AsyncSession, user_id: int) -> list[SysUserToken]:
    return list(
        await db.scalars(
            select(SysUserToken)
            .where(SysUserToken.user_id == user_id)
            .order_by(SysUserToken.token_id.desc())
        )
    )


async def test_the_current_session_is_listed(
    client: AsyncClient, admin_headers: dict[str, str], admin_user: SysUser
) -> None:
    resp = await client.get(ONLINE_URL, headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"rows", "total"}
    assert data["total"] >= 1
    row = data["rows"][0]
    assert row["user_name"] == "admin"
    assert {"browser", "os", "login_ip", "login_time", "access_jti"} <= set(row)


async def test_revoked_sessions_are_hidden(
    client: AsyncClient, admin_user: SysUser, login, db_session: AsyncSession
) -> None:
    await login("admin")  # 较早的会话
    current = await login("admin")  # 当前用的会话

    before = (await client.get(ONLINE_URL, headers=current)).json()["data"]["total"]
    rows = (await client.get(ONLINE_URL, headers=current)).json()["data"]["rows"]
    victim_jti = rows[-1]["access_jti"]  # 最旧的一条，肯定不是当前这个

    victim = await db_session.scalar(
        select(SysUserToken).where(SysUserToken.access_jti == victim_jti)
    )
    assert victim is not None
    victim.revoked = True
    await db_session.flush()

    after = (await client.get(ONLINE_URL, headers=current)).json()["data"]["total"]
    assert after == before - 1


async def test_expired_sessions_are_hidden(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, admin_user: SysUser
) -> None:
    """refresh 也过期的会话不再算「在线」。"""
    before = (await client.get(ONLINE_URL, headers=admin_headers)).json()["data"]["total"]

    session = (await _sessions(db_session, admin_user.user_id))[0]
    session.refresh_expire = utcnow() - timedelta(seconds=1)
    await db_session.flush()

    after = (await client.get(ONLINE_URL, headers=admin_headers)).json()["data"]["total"]
    assert after == before - 1


async def test_filters_by_user_name(
    client: AsyncClient, admin_headers: dict[str, str], admin_user: SysUser
) -> None:
    mine = await client.get(ONLINE_URL, headers=admin_headers, params={"user_name": "admin"})
    other = await client.get(ONLINE_URL, headers=admin_headers, params={"user_name": "no_such_user"})

    assert mine.json()["data"]["total"] >= 1
    assert other.json()["data"]["total"] == 0


async def test_force_logout_kills_that_session(
    client: AsyncClient, admin_user: SysUser, login, db_session: AsyncSession
) -> None:
    """强退的判据是「那个会话的下一次请求被拒」，不是「字段被改成 True」。"""
    first = await login("admin")  # 较早的会话
    second = await login("admin")  # 当前用于管理操作的会话

    rows = (await client.get(ONLINE_URL, headers=second)).json()["data"]["rows"]
    assert len(rows) >= 2
    oldest = rows[-1]["access_jti"]

    resp = await client.delete(f"{ONLINE_URL}/{oldest}", headers=second)
    assert resp.status_code == 200

    # 用被强退的那个令牌发请求 —— 应当 401
    assert (await client.get("/api/v1/auth/profile", headers=first)).status_code == 401
    # 自己的会话不受影响
    assert (await client.get("/api/v1/auth/profile", headers=second)).status_code == 200


async def test_cannot_force_logout_yourself(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, admin_user: SysUser
) -> None:
    mine = (await _sessions(db_session, admin_user.user_id))[0]

    resp = await client.delete(f"{ONLINE_URL}/{mine.access_jti}", headers=admin_headers)

    assert resp.status_code == 400
    assert "自己" in resp.json()["msg"]


async def test_unknown_session_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.delete(f"{ONLINE_URL}/not-a-real-jti", headers=admin_headers)

    assert resp.status_code == 400
    assert "不存在" in resp.json()["msg"]


async def test_login_purges_the_accounts_dead_sessions(
    client: AsyncClient, db_session: AsyncSession, admin_user: SysUser, login, admin_headers: dict[str, str]
) -> None:
    """表从 P0 起只增不减；登录时的按用户清理把它变成有界增长。"""
    db_session.add(
        SysUserToken(
            user_id=admin_user.user_id,
            access_jti="dead-access",
            access_expire=utcnow() - timedelta(days=10),
            refresh_jti="dead-refresh",
            refresh_expire=utcnow() - timedelta(days=2),
            login_ip="127.0.0.1",
            browser="old",
            os="old",
            login_time=utcnow() - timedelta(days=10),
            revoked=False,
        )
    )
    await db_session.flush()
    assert await db_session.scalar(
        select(func.count()).select_from(SysUserToken).where(SysUserToken.access_jti == "dead-access")
    )

    await login("admin")

    assert (
        await db_session.scalar(
            select(func.count()).select_from(SysUserToken).where(SysUserToken.access_jti == "dead-access")
        )
        == 0
    )


async def test_live_sessions_survive_the_purge(
    client: AsyncClient, db_session: AsyncSession, admin_user: SysUser, login, admin_headers: dict[str, str]
) -> None:
    """清理只能删「彻底失效」的，不能把别人正在用的会话一并带走。"""
    before = int(
        await db_session.scalar(
            select(func.count()).select_from(SysUserToken).where(SysUserToken.user_id == admin_user.user_id)
        )
        or 0
    )

    await login("admin")

    after = int(
        await db_session.scalar(
            select(func.count()).select_from(SysUserToken).where(SysUserToken.user_id == admin_user.user_id)
        )
        or 0
    )
    # 新增一行（本次登录），已有会话一条都没被删
    assert after == before + 1


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(ONLINE_URL)).status_code == 401


async def test_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    assert (await client.get(ONLINE_URL, headers=staff_headers)).status_code == 403
