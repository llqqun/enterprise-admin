"""参数配置：CRUD 与按键查询。

`is_builtin` 的行**可以改值，但不能删**。删掉 `sys.account.captchaEnabled` 并不会「关闭验证码」——
它会让读取方落到自己的兜底值，行为被悄悄改掉，而页面上看不出任何异常。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum
from app.core.exceptions import BusinessException, NotFoundException
from app.core.response import PageParams
from app.models.config import SysConfig


async def _assert_key_free(db: AsyncSession, key: str, *, exclude_id: int | None = None) -> None:
    statement = select(SysConfig.config_id).where(SysConfig.config_key == key)
    if exclude_id is not None:
        statement = statement.where(SysConfig.config_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("参数键名已存在")


async def list_configs(
    db: AsyncSession,
    params: PageParams,
    *,
    config_name: str | None = None,
    config_key: str | None = None,
) -> tuple[list[SysConfig], int]:
    statement = select(SysConfig)
    if config_name:
        statement = statement.where(SysConfig.config_name.contains(config_name))
    if config_key:
        statement = statement.where(SysConfig.config_key.contains(config_key))

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysConfig.config_id).limit(params.page_size).offset(offset)
        )
    )
    return rows, total


async def get_config(db: AsyncSession, config_id: int) -> SysConfig:
    row = await db.scalar(select(SysConfig).where(SysConfig.config_id == config_id))
    if row is None:
        raise NotFoundException("参数不存在")
    return row


async def get_value(db: AsyncSession, config_key: str) -> str:
    """按键取值。业务代码要读配置时走这里，而不是自己去拼 SQL。"""
    row = await db.scalar(select(SysConfig).where(SysConfig.config_key == config_key))
    if row is None:
        raise NotFoundException("参数不存在")
    return row.config_value


async def create_config(db: AsyncSession, payload) -> SysConfig:
    await _assert_key_free(db, payload.config_key)
    row = SysConfig(
        config_name=payload.config_name,
        config_key=payload.config_key,
        config_value=payload.config_value,
        is_builtin=payload.is_builtin,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(row)
    await db.flush()
    # 输出 schema 里有 create_time（server_default），不 refresh 会在 Pydantic 取属性时
    # 触发惰性 SELECT，在异步上下文里抛 MissingGreenlet。
    await db.refresh(row)
    return row


async def update_config(db: AsyncSession, payload) -> SysConfig:
    row = await get_config(db, payload.config_id)
    await _assert_key_free(db, payload.config_key, exclude_id=row.config_id)

    row.config_name = payload.config_name
    row.config_key = payload.config_key
    row.config_value = payload.config_value
    # `is_builtin` 允许改：把一个自建参数标记成内置是合理的收紧动作。
    row.is_builtin = payload.is_builtin
    row.remark = payload.remark
    await db.flush()
    await db.refresh(row)
    return row


async def delete_configs(db: AsyncSession, config_ids: list[int]) -> None:
    rows = list(await db.scalars(select(SysConfig).where(SysConfig.config_id.in_(config_ids))))
    builtin = [row.config_key for row in rows if row.is_builtin]
    if builtin:
        raise BusinessException(f"系统内置参数不允许删除：{', '.join(builtin)}")

    for row in rows:
        row.del_flag = DelFlagEnum.DELETED
    await db.flush()
