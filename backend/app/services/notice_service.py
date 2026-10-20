"""通知公告。

`status` 是**已发布 / 已撤回**，不是启用 / 停用。撤回一条公告的预期是它从展示处消失，
所以 `latest_notices()` 只返回已发布的那些 —— 否则「撤回」只是个装饰。

v-html 的风险在这里被显式处理：公告正文是管理员录入的富文本，前端用 `v-html` 渲染。
这意味着**谁能编辑公告，谁就能在这个站点上执行脚本**。所以编辑权限必须严格限制，
这一点写进了 README 的已知取舍。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.core.exceptions import NotFoundException
from app.core.response import PageParams
from app.models.notice import SysNotice


async def list_notices(
    db: AsyncSession,
    params: PageParams,
    *,
    notice_title: str | None = None,
    notice_type: str | None = None,
    status: str | None = None,
) -> tuple[list[SysNotice], int]:
    statement = select(SysNotice)
    if notice_title:
        statement = statement.where(SysNotice.notice_title.contains(notice_title))
    if notice_type:
        statement = statement.where(SysNotice.notice_type == notice_type)
    if status:
        statement = statement.where(SysNotice.status == status)

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysNotice.notice_id.desc()).limit(params.page_size).offset(offset)
        )
    )
    return rows, total


async def latest_notices(db: AsyncSession, limit: int = 5) -> list[SysNotice]:
    """首页用：只给已发布的，最新的在前。"""
    return list(
        await db.scalars(
            select(SysNotice)
            .where(SysNotice.status == StatusEnum.NORMAL)
            .order_by(SysNotice.notice_id.desc())
            .limit(limit)
        )
    )


async def get_notice(db: AsyncSession, notice_id: int) -> SysNotice:
    row = await db.scalar(select(SysNotice).where(SysNotice.notice_id == notice_id))
    if row is None:
        raise NotFoundException("公告不存在")
    return row


async def create_notice(db: AsyncSession, payload) -> SysNotice:
    row = SysNotice(
        notice_title=payload.notice_title,
        notice_type=payload.notice_type,
        notice_content=payload.notice_content,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(row)
    await db.flush()
    # 输出 schema 里含 create_time（server_default），不 refresh 会在 Pydantic 取属性时触发
    # 惰性 SELECT，在异步上下文里抛 MissingGreenlet。
    await db.refresh(row)
    return row


async def update_notice(db: AsyncSession, payload) -> SysNotice:
    row = await get_notice(db, payload.notice_id)
    row.notice_title = payload.notice_title
    row.notice_type = payload.notice_type
    row.notice_content = payload.notice_content
    row.status = payload.status
    row.remark = payload.remark
    await db.flush()
    await db.refresh(row)
    return row


async def delete_notices(db: AsyncSession, notice_ids: list[int]) -> None:
    rows = list(await db.scalars(select(SysNotice).where(SysNotice.notice_id.in_(notice_ids))))
    for row in rows:
        row.del_flag = DelFlagEnum.DELETED
    await db.flush()
