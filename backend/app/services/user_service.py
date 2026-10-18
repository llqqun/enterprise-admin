"""用户查询。

**数据权限在这里真正生效**：`list_users` 是第一个把 `apply_data_scope` 接到查询上的接口。
业务代码里没有任何 `if is_admin` —— 范围判断只有一处实现，这是它不漂移的前提。
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ADMIN_ROLE_KEY, DelFlagEnum, StatusEnum
from app.core.deps import CurrentUser
from app.core.exceptions import BusinessException, NotFoundException
from app.core.response import PageParams
from app.core.security import hash_password
from app.models.associations import SysUserPost, SysUserRole
from app.models.post import SysPost
from app.models.role import SysRole
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


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------


async def get_user(db: AsyncSession, user_id: int) -> SysUser:
    user = await db.scalar(select(SysUser).where(SysUser.user_id == user_id))
    if user is None:
        raise NotFoundException("用户不存在")
    return user


async def _assert_user_name_free(
    db: AsyncSession, user_name: str, *, exclude_id: int | None = None
) -> None:
    statement = select(SysUser.user_id).where(SysUser.user_name == user_name)
    if exclude_id is not None:
        statement = statement.where(SysUser.user_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("用户名已存在")


async def _known_role_ids(db: AsyncSession, role_ids: list[int]) -> list[int]:
    requested = sorted(set(role_ids))
    if not requested:
        return []
    known = set(await db.scalars(select(SysRole.role_id).where(SysRole.role_id.in_(requested))))
    unknown = [item for item in requested if item not in known]
    if unknown:
        raise BusinessException(f"角色不存在：{unknown}")
    return requested


async def _known_post_ids(db: AsyncSession, post_ids: list[int]) -> list[int]:
    requested = sorted(set(post_ids))
    if not requested:
        return []
    known = set(await db.scalars(select(SysPost.post_id).where(SysPost.post_id.in_(requested))))
    unknown = [item for item in requested if item not in known]
    if unknown:
        raise BusinessException(f"岗位不存在：{unknown}")
    return requested


async def _replace_roles(db: AsyncSession, user_id: int, role_ids: list[int]) -> None:
    await db.execute(delete(SysUserRole).where(SysUserRole.user_id == user_id))
    for role_id in role_ids:
        db.add(SysUserRole(user_id=user_id, role_id=role_id))


async def _replace_posts(db: AsyncSession, user_id: int, post_ids: list[int]) -> None:
    await db.execute(delete(SysUserPost).where(SysUserPost.user_id == user_id))
    for post_id in post_ids:
        db.add(SysUserPost(user_id=user_id, post_id=post_id))


async def _assert_not_last_admin(db: AsyncSession, user_ids: list[int]) -> None:
    """系统必须至少留下一个启用状态的超管。

    删掉最后一个超管之后，没有任何接口能再把人提上来 —— 数据库是唯一入口。这类自锁是后台里
    最难恢复的故障，所以宁可在这里挡住。
    """
    admin_role_id = await db.scalar(select(SysRole.role_id).where(SysRole.role_key == ADMIN_ROLE_KEY))
    if admin_role_id is None:
        return

    targets = set(user_ids)
    holds_admin = set(
        await db.scalars(
            select(SysUserRole.user_id).where(
                SysUserRole.role_id == admin_role_id, SysUserRole.user_id.in_(targets)
            )
        )
    )
    if not holds_admin:
        return

    remaining = int(
        await db.scalar(
            select(func.count())
            .select_from(SysUserRole)
            .join(SysUser, SysUser.user_id == SysUserRole.user_id)
            .where(
                SysUserRole.role_id == admin_role_id,
                SysUser.status == StatusEnum.NORMAL,
                SysUser.user_id.not_in(targets),
            )
        )
        or 0
    )
    if remaining == 0:
        raise BusinessException("系统必须保留至少一个超级管理员")


async def create_user(db: AsyncSession, payload) -> SysUser:
    await _assert_user_name_free(db, payload.user_name)
    role_ids = await _known_role_ids(db, payload.role_ids)
    post_ids = await _known_post_ids(db, payload.post_ids)

    user = SysUser(
        user_name=payload.user_name,
        nick_name=payload.nick_name,
        password=hash_password(payload.password),
        dept_id=payload.dept_id,
        email=payload.email,
        phonenumber=payload.phonenumber,
        sex=payload.sex,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(user)
    await db.flush()

    await _replace_roles(db, user.user_id, role_ids)
    await _replace_posts(db, user.user_id, post_ids)
    await db.flush()
    return user


async def update_user(db: AsyncSession, payload) -> SysUser:
    user = await get_user(db, payload.user_id)
    await _assert_user_name_free(db, payload.user_name, exclude_id=user.user_id)
    role_ids = await _known_role_ids(db, payload.role_ids)
    post_ids = await _known_post_ids(db, payload.post_ids)

    user.user_name = payload.user_name
    user.nick_name = payload.nick_name
    user.dept_id = payload.dept_id
    user.email = payload.email
    user.phonenumber = payload.phonenumber
    user.sex = payload.sex
    user.status = payload.status
    user.remark = payload.remark

    await _replace_roles(db, user.user_id, role_ids)
    await _replace_posts(db, user.user_id, post_ids)
    await db.flush()
    return user


async def delete_users(db: AsyncSession, user_ids: list[int], current: CurrentUser) -> None:
    if current.user_id in user_ids:
        raise BusinessException("不能删除自己的账号")

    users = list(await db.scalars(select(SysUser).where(SysUser.user_id.in_(user_ids))))
    await _assert_not_last_admin(db, [user.user_id for user in users])

    for user in users:
        user.del_flag = DelFlagEnum.DELETED
    await db.flush()


async def reset_password(db: AsyncSession, user_id: int, password: str) -> None:
    user = await get_user(db, user_id)
    user.password = hash_password(password)
    await db.flush()


async def change_status(
    db: AsyncSession, user_id: int, status: str, current: CurrentUser
) -> None:
    if status != StatusEnum.NORMAL and user_id == current.user_id:
        raise BusinessException("不能停用自己的账号")

    user = await get_user(db, user_id)
    if status != StatusEnum.NORMAL:
        await _assert_not_last_admin(db, [user_id])

    user.status = status
    await db.flush()