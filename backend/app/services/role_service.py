"""角色：CRUD、菜单授权、数据范围与用户授权。

本模块有两处「不做就会丢掉整个系统」的守卫，都被测试单独钉住：

1. **自锁**：`admin` 角色不能被删除、停用，其 `role_key` 也不能被改。三者任一发生，
   就再也没有人能进入后台了（改 key 会同时让通配权限失效）。
2. **数据范围切换时要清空旧的自定义部门**：否则把范围从「自定义」改成「本部门」再改回来，
   旧的 `sys_role_dept` 会静静地让范围比预期更宽。
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ADMIN_ROLE_KEY, DataScopeEnum, DelFlagEnum, StatusEnum
from app.core.exceptions import BusinessException, NotFoundException
from app.core.response import PageParams
from app.models.associations import SysRoleDept, SysRoleMenu, SysUserRole
from app.models.dept import SysDept
from app.models.role import SysRole
from app.models.user import SysUser
from app.schemas.system import RoleCreate, RoleDataScope, RoleUpdate

ADMIN_LOCK_MSG = "超级管理员角色是内置的，不允许删除、停用或修改权限字符串"


def _assert_not_admin(role: SysRole) -> None:
    if role.role_key == ADMIN_ROLE_KEY:
        raise BusinessException(ADMIN_LOCK_MSG)


async def _assert_role_key_free(
    db: AsyncSession, role_key: str, *, exclude_id: int | None = None
) -> None:
    statement = select(SysRole.role_id).where(SysRole.role_key == role_key)
    if exclude_id is not None:
        statement = statement.where(SysRole.role_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("角色权限字符串已存在")


async def _clear_links(db: AsyncSession, role_ids: list[int]) -> None:
    await db.execute(delete(SysRoleMenu).where(SysRoleMenu.role_id.in_(role_ids)))
    await db.execute(delete(SysRoleDept).where(SysRoleDept.role_id.in_(role_ids)))
    await db.execute(delete(SysUserRole).where(SysUserRole.role_id.in_(role_ids)))


def _filtered(*, role_name: str | None = None, role_key: str | None = None, status: str | None = None):
    statement = select(SysRole)
    if role_name:
        statement = statement.where(SysRole.role_name.contains(role_name))
    if role_key:
        statement = statement.where(SysRole.role_key == role_key)
    if status:
        statement = statement.where(SysRole.status == status)
    return statement


async def list_roles(
    db: AsyncSession,
    params: PageParams,
    *,
    role_name: str | None = None,
    role_key: str | None = None,
    status: str | None = None,
) -> tuple[list[SysRole], int]:
    statement = _filtered(role_name=role_name, role_key=role_key, status=status)
    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysRole.role_sort, SysRole.role_id)
            .limit(params.page_size)
            .offset(offset)
        )
    )
    return rows, total


async def get_role(db: AsyncSession, role_id: int) -> SysRole:
    role = await db.scalar(select(SysRole).where(SysRole.role_id == role_id))
    if role is None:
        raise NotFoundException("角色不存在")
    return role


async def create_role(db: AsyncSession, payload: RoleCreate) -> SysRole:
    await _assert_role_key_free(db, payload.role_key)
    role = SysRole(
        role_name=payload.role_name,
        role_key=payload.role_key,
        role_sort=payload.role_sort,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return role


async def update_role(db: AsyncSession, payload: RoleUpdate) -> SysRole:
    role = await get_role(db, payload.role_id)

    if role.role_key == ADMIN_ROLE_KEY:
        if payload.role_key != ADMIN_ROLE_KEY:
            raise BusinessException(ADMIN_LOCK_MSG)
        if payload.status != StatusEnum.NORMAL:
            raise BusinessException(ADMIN_LOCK_MSG)

    await _assert_role_key_free(db, payload.role_key, exclude_id=role.role_id)

    role.role_name = payload.role_name
    role.role_key = payload.role_key
    role.role_sort = payload.role_sort
    role.status = payload.status
    role.remark = payload.remark
    await db.flush()
    await db.refresh(role)
    return role


async def delete_roles(db: AsyncSession, role_ids: list[int]) -> None:
    roles = list(await db.scalars(select(SysRole).where(SysRole.role_id.in_(role_ids))))
    for role in roles:
        _assert_not_admin(role)

    await _clear_links(db, [role.role_id for role in roles])
    for role in roles:
        role.del_flag = DelFlagEnum.DELETED
    await db.flush()


async def change_status(db: AsyncSession, role_id: int, status: str) -> SysRole:
    role = await get_role(db, role_id)
    if status != StatusEnum.NORMAL:
        _assert_not_admin(role)
    role.status = status
    await db.flush()
    await db.refresh(role)
    return role


async def set_data_scope(db: AsyncSession, payload: RoleDataScope) -> SysRole:
    role = await get_role(db, payload.role_id)
    _assert_not_admin(role)

    requested = sorted(set(payload.dept_ids))
    if requested:
        known = set(await db.scalars(select(SysDept.dept_id).where(SysDept.dept_id.in_(requested))))
        unknown = [dept_id for dept_id in requested if dept_id not in known]
        if unknown:
            # `sys_role_dept.dept_id` is a foreign key, so without this check the
            # caller gets an opaque 500 from the database instead of being told
            # which id was wrong.
            raise BusinessException(f"部门不存在：{unknown}")

    await db.execute(delete(SysRoleDept).where(SysRoleDept.role_id == role.role_id))
    if int(payload.data_scope) == int(DataScopeEnum.CUSTOM):
        for dept_id in requested:
            db.add(SysRoleDept(role_id=role.role_id, dept_id=dept_id))

    role.data_scope = payload.data_scope
    await db.flush()
    await db.refresh(role)
    return role


# ---------------------------------------------------------------------------
# 用户授权
# ---------------------------------------------------------------------------


async def _users_for(
    db: AsyncSession, params: PageParams, role_id: int, *, allocated: bool
):
    member_ids = select(SysUserRole.user_id).where(SysUserRole.role_id == role_id)
    statement = select(SysUser)
    statement = (
        statement.where(SysUser.user_id.in_(member_ids))
        if allocated
        else statement.where(SysUser.user_id.not_in(member_ids))
    )

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(statement.order_by(SysUser.user_id).limit(params.page_size).offset(offset))
    )
    return rows, total


async def allocated_users(db: AsyncSession, params: PageParams, role_id: int):
    await get_role(db, role_id)
    return await _users_for(db, params, role_id, allocated=True)


async def unallocated_users(db: AsyncSession, params: PageParams, role_id: int):
    await get_role(db, role_id)
    return await _users_for(db, params, role_id, allocated=False)


async def grant_users(db: AsyncSession, role_id: int, user_ids: list[int]) -> None:
    """幂等授权：已经拥有该角色的用户不会被重复插入。"""
    await get_role(db, role_id)
    if not user_ids:
        return

    existing = set(
        await db.scalars(
            select(SysUserRole.user_id).where(
                SysUserRole.role_id == role_id, SysUserRole.user_id.in_(user_ids)
            )
        )
    )
    known = set(await db.scalars(select(SysUser.user_id).where(SysUser.user_id.in_(user_ids))))
    for user_id in sorted(known - existing):
        db.add(SysUserRole(user_id=user_id, role_id=role_id))
    await db.flush()


async def revoke_user(db: AsyncSession, role_id: int, user_id: int) -> None:
    await get_role(db, role_id)
    await db.execute(
        delete(SysUserRole).where(SysUserRole.role_id == role_id, SysUserRole.user_id == user_id)
    )
    await db.flush()


async def revoke_all(db: AsyncSession, role_id: int) -> None:
    await get_role(db, role_id)
    await db.execute(delete(SysUserRole).where(SysUserRole.role_id == role_id))
    await db.flush()
