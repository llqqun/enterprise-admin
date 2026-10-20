"""登录日志查询（只读）。

数据从 P0 起就在写（每次登录成功与失败都落一行，`sys_login_log`），这里只补上「读」。
刻意不提供删除接口：审计日志能被接口删掉，等于审计可被抹除 ——
真要清理应当是一次受控的运维动作，而不是页面上的一个按钮。
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessException
from app.core.response import PageParams
from app.models.login_log import SysLoginLog


def _parse_date(value: str, *, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise BusinessException(f"{field} 不是合法的日期（应为 YYYY-MM-DD）") from None


async def list_login_logs(
    db: AsyncSession,
    params: PageParams,
    *,
    user_name: str | None = None,
    status: str | None = None,
    begin_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[SysLoginLog], int]:
    statement = select(SysLoginLog)

    if user_name:
        statement = statement.where(SysLoginLog.user_name.contains(user_name))
    if status:
        statement = statement.where(SysLoginLog.status == status)
    if begin_date:
        start = datetime.combine(_parse_date(begin_date, field="开始日期"), time.min)
        statement = statement.where(SysLoginLog.login_time >= start)
    if end_date:
        # 结束日期是**闭区间**：查 10-20 应该包含 10-20 整天的记录，
        # 所以用「次日零点之前」而不是「<= 10-20 00:00:00」。
        stop = datetime.combine(_parse_date(end_date, field="结束日期") + timedelta(days=1), time.min)
        statement = statement.where(SysLoginLog.login_time < stop)

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysLoginLog.login_time.desc(), SysLoginLog.info_id.desc())
            .limit(params.page_size)
            .offset(offset)
        )
    )
    return rows, total
