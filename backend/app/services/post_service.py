"""岗位：分页 CRUD 与业务键唯一性。

`post_code` 是业务键，但**没有数据库唯一索引** —— 逻辑删除后必须允许重建同名/同码岗位，
所以唯一性只能在 service 层、事务内校验。这正是 P0 设计文档承诺过却从未写下的那条校验。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.core.exceptions import BusinessException, NotFoundException
from app.core.response import PageParams
from app.models.post import SysPost
from app.schemas.system import PostCreate, PostUpdate


async def _assert_code_free(db: AsyncSession, post_code: str, *, exclude_id: int | None = None) -> None:
    statement = select(SysPost.post_id).where(SysPost.post_code == post_code)
    if exclude_id is not None:
        statement = statement.where(SysPost.post_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("岗位编码已存在")


def _filtered(
    *, post_code: str | None = None, post_name: str | None = None, status: str | None = None
):
    statement = select(SysPost)
    if post_code:
        statement = statement.where(SysPost.post_code == post_code)
    if post_name:
        statement = statement.where(SysPost.post_name.contains(post_name))
    if status:
        statement = statement.where(SysPost.status == status)
    return statement


async def list_posts(
    db: AsyncSession,
    params: PageParams,
    *,
    post_code: str | None = None,
    post_name: str | None = None,
    status: str | None = None,
) -> tuple[list[SysPost], int]:
    statement = _filtered(post_code=post_code, post_name=post_name, status=status)

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysPost.post_sort, SysPost.post_id)
            .limit(params.page_size)
            .offset(offset)
        )
    )
    return rows, total


async def post_options(db: AsyncSession) -> list[SysPost]:
    """下拉选项只给启用的岗位：停用岗位不该还能被新用户选中。"""
    return list(
        await db.scalars(
            select(SysPost)
            .where(SysPost.status == StatusEnum.NORMAL)
            .order_by(SysPost.post_sort, SysPost.post_id)
        )
    )


async def get_post(db: AsyncSession, post_id: int) -> SysPost:
    post = await db.scalar(select(SysPost).where(SysPost.post_id == post_id))
    if post is None:
        raise NotFoundException("岗位不存在")
    return post


async def create_post(db: AsyncSession, payload: PostCreate) -> SysPost:
    await _assert_code_free(db, payload.post_code)
    post = SysPost(
        post_code=payload.post_code,
        post_name=payload.post_name,
        post_sort=payload.post_sort,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(post)
    await db.flush()
    # `create_time` carries a server default, so its value exists only in the
    # database. Reading it without this refresh would issue a lazy SELECT from
    # inside Pydantic's attribute access, where there is no greenlet to await on.
    await db.refresh(post)
    return post


async def update_post(db: AsyncSession, payload: PostUpdate) -> SysPost:
    post = await get_post(db, payload.post_id)
    await _assert_code_free(db, payload.post_code, exclude_id=post.post_id)

    post.post_code = payload.post_code
    post.post_name = payload.post_name
    post.post_sort = payload.post_sort
    post.status = payload.status
    post.remark = payload.remark
    await db.flush()
    await db.refresh(post)
    return post


async def delete_posts(db: AsyncSession, post_ids: list[int]) -> None:
    """批量软删。不存在的 ID 静默跳过 —— 删除是幂等的，重复提交不该报错。"""
    posts = list(await db.scalars(select(SysPost).where(SysPost.post_id.in_(post_ids))))
    for post in posts:
        post.del_flag = DelFlagEnum.DELETED
    await db.flush()
