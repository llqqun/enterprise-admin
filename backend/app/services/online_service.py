"""在线用户：查询活动会话与强制下线。

「在线」的判据是 **refresh 令牌还没过期且未被撤销**，而不是 access 令牌 —— 后者 30 分钟就到期，
用它判断会把一个仍在使用系统的人显示成离线。

表 `sys_user_token` 从 P0 起只增不减（`docs/P1决策记录.md` 的一条遗留）。这里用**按用户惰性清理**
解决：每次登录时删掉该用户已经彻底失效（refresh 也过期）的行。不引入后台任务，
因为后台任务会活得比事件循环长，在测试里制造串扰（P0 的裁定）。
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.exceptions import BusinessException
from app.core.response import PageParams
from app.models.token import SysUserToken
from app.models.user import SysUser
from app.utils.timeutil import utcnow


def _live_condition(now: datetime):
    return SysUserToken.revoked.is_(False), SysUserToken.refresh_expire > now


async def list_sessions(
    db: AsyncSession,
    params: PageParams,
    *,
    user_name: str | None = None,
    login_ip: str | None = None,
) -> tuple[list[dict], int]:
    now = utcnow()
    revoked_off, not_expired = _live_condition(now)

    statement = (
        select(
            SysUserToken.token_id,
            SysUserToken.access_jti,
            SysUserToken.login_ip,
            SysUserToken.browser,
            SysUserToken.os,
            SysUserToken.login_time,
            SysUserToken.refresh_expire,
            SysUser.user_name,
            SysUser.nick_name,
        )
        .join(SysUser, SysUser.user_id == SysUserToken.user_id)
        .where(revoked_off, not_expired)
    )
    if user_name:
        statement = statement.where(SysUser.user_name.contains(user_name))
    if login_ip:
        statement = statement.where(SysUserToken.login_ip.contains(login_ip))

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = (
        await db.execute(
            statement.order_by(SysUserToken.login_time.desc(), SysUserToken.token_id.desc())
            .limit(params.page_size)
            .offset(offset)
        )
    ).all()

    return [
        {
            "token_id": row.token_id,
            "access_jti": row.access_jti,
            "user_name": row.user_name,
            "nick_name": row.nick_name,
            "login_ip": row.login_ip,
            "browser": row.browser,
            "os": row.os,
            "login_time": row.login_time,
            "refresh_expire": row.refresh_expire,
        }
        for row in rows
    ], total


async def force_logout(db: AsyncSession, access_jti: str, current: CurrentUser) -> None:
    """把某个会话标记为撤销。撤销后该会话的下一次请求就会 401。"""
    if access_jti == current.access_jti:
        # 强退自己等于「用强制手段把自己踢出去」，而退出登录就在手边。
        # 允许它只会让人先按错再找原因。
        raise BusinessException("不能强制下线自己的会话，请使用退出登录")

    session = await db.scalar(
        select(SysUserToken).where(SysUserToken.access_jti == access_jti)
    )
    if session is None:
        raise BusinessException("会话不存在或已结束")

    session.revoked = True
    await db.flush()


async def purge_dead_sessions(db: AsyncSession, user_id: int) -> int:
    """删掉该用户已经彻底失效的会话记录（refresh 也过期了）。返回删除行数。

    只按**用户**清理而不是全表：全表删除会让一次登录变成一次可能很慢的批量写。
    """
    result = await db.execute(
        delete(SysUserToken).where(
            SysUserToken.user_id == user_id,
            SysUserToken.refresh_expire < utcnow() - timedelta(seconds=0),
        )
    )
    await db.flush()
    return result.rowcount or 0
