"""用户查询。

**数据权限在这里真正生效**：`list_users` 是第一个把 `apply_data_scope` 接到查询上的接口。
业务代码里没有任何 `if is_admin` —— 范围判断只有一处实现，这是它不漂移的前提。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import PageParams
from app.models.user import SysUser
from app.services.data_scope import apply_data_scope


def _filtered(*, user_name: str | None = None, status: str | None = None):
    statement = select(SysUser)
    if user_name:
        statement = statement.where(SysUser.user_name.contains(user_name))
    if status:
        statement = statement.where(SysUser.status == status)
    return statement


async def list_users(
    db: AsyncSession,
    params: PageParams,
    user: CurrentUser,
    *,
    user_name: str | None = None,
    status: str | None = None,
) -> tuple[list[SysUser], int]:
    """分页列出可见用户。

    `total` 必须基于**已施加数据权限**的语句统计：用全表总数配可见行，前端会算出并不存在的页数，
    用户翻到第 2 页看到空白。
    """
    statement = await apply_data_scope(
        db, _filtered(user_name=user_name, status=status), SysUser, user.data_scope
    )

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysUser.user_id).limit(params.page_size).offset(offset)
        )
    )
    return rows, total
