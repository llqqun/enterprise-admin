"""字典：类型与数据的增删改查。

两条容易做错的地方：

1. **改类型的 `dict_type` 必须级联到数据行**。`sys_dict_data` 是按 `dict_type` 字符串关联的
   （没有外键），改了类型名却不同步，那一整组选项就会变成孤儿 —— 页面上表现为「选项突然全没了」。
2. **删类型前要确认没有数据行**，否则同样留下一组孤儿选项。
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.core.exceptions import BusinessException, NotFoundException
from app.core.response import PageParams
from app.models.dict import SysDictData, SysDictType

# ---------------------------------------------------------------------------
# 字典类型
# ---------------------------------------------------------------------------


async def _assert_dict_type_free(
    db: AsyncSession, dict_type: str, *, exclude_id: int | None = None
) -> None:
    statement = select(SysDictType.dict_id).where(SysDictType.dict_type == dict_type)
    if exclude_id is not None:
        statement = statement.where(SysDictType.dict_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("字典类型已存在")


async def list_types(
    db: AsyncSession,
    params: PageParams,
    *,
    dict_name: str | None = None,
    dict_type: str | None = None,
    status: str | None = None,
) -> tuple[list[SysDictType], int]:
    statement = select(SysDictType)
    if dict_name:
        statement = statement.where(SysDictType.dict_name.contains(dict_name))
    if dict_type:
        statement = statement.where(SysDictType.dict_type.contains(dict_type))
    if status:
        statement = statement.where(SysDictType.status == status)

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysDictType.dict_id).limit(params.page_size).offset(offset)
        )
    )
    return rows, total


async def get_type(db: AsyncSession, dict_id: int) -> SysDictType:
    row = await db.scalar(select(SysDictType).where(SysDictType.dict_id == dict_id))
    if row is None:
        raise NotFoundException("字典类型不存在")
    return row


async def create_type(db: AsyncSession, payload) -> SysDictType:
    await _assert_dict_type_free(db, payload.dict_type)
    row = SysDictType(
        dict_name=payload.dict_name,
        dict_type=payload.dict_type,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(row)
    await db.flush()
    # 输出 schema 里有 create_time（server_default），flush 后它只存在于数据库里；
    # 不 refresh 的话 Pydantic 取属性时会触发惰性 SELECT，在异步上下文里抛 MissingGreenlet。
    await db.refresh(row)
    return row


async def update_type(db: AsyncSession, payload) -> SysDictType:
    row = await get_type(db, payload.dict_id)
    await _assert_dict_type_free(db, payload.dict_type, exclude_id=row.dict_id)

    old_type = row.dict_type
    row.dict_name = payload.dict_name
    row.dict_type = payload.dict_type
    row.status = payload.status
    row.remark = payload.remark

    if old_type != payload.dict_type:
        # 级联：不这么做的话，改完类型名那一整组选项就成了孤儿，
        # 而界面上只会表现为「选项全没了」，几乎不可能当场联想到改名。
        await db.execute(
            update(SysDictData)
            .where(SysDictData.dict_type == old_type)
            .values(dict_type=payload.dict_type)
        )

    await db.flush()
    await db.refresh(row)
    return row


async def delete_types(db: AsyncSession, dict_ids: list[int]) -> None:
    rows = list(await db.scalars(select(SysDictType).where(SysDictType.dict_id.in_(dict_ids))))
    for row in rows:
        has_data = await db.scalar(
            select(SysDictData.dict_code).where(SysDictData.dict_type == row.dict_type).limit(1)
        )
        if has_data is not None:
            raise BusinessException(f"字典「{row.dict_name}」下还有数据，不允许删除")

    for row in rows:
        row.del_flag = DelFlagEnum.DELETED
    await db.flush()


# ---------------------------------------------------------------------------
# 字典数据
# ---------------------------------------------------------------------------


async def list_data(
    db: AsyncSession,
    params: PageParams,
    *,
    dict_type: str | None = None,
    dict_label: str | None = None,
    status: str | None = None,
) -> tuple[list[SysDictData], int]:
    statement = select(SysDictData)
    if dict_type:
        statement = statement.where(SysDictData.dict_type == dict_type)
    if dict_label:
        statement = statement.where(SysDictData.dict_label.contains(dict_label))
    if status:
        statement = statement.where(SysDictData.status == status)

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysDictData.dict_sort, SysDictData.dict_code)
            .limit(params.page_size)
            .offset(offset)
        )
    )
    return rows, total


async def data_by_type(db: AsyncSession, dict_type: str) -> list[SysDictData]:
    """给前端渲染标签/下拉用：只返回**启用**的选项，按排序号。

    类型本身停用时返回空 —— 停用一个字典的意图就是「别再用了」。
    """
    parent = await db.scalar(
        select(SysDictType).where(SysDictType.dict_type == dict_type)
    )
    if parent is None or parent.status != StatusEnum.NORMAL:
        return []
    return list(
        await db.scalars(
            select(SysDictData)
            .where(SysDictData.dict_type == dict_type, SysDictData.status == StatusEnum.NORMAL)
            .order_by(SysDictData.dict_sort, SysDictData.dict_code)
        )
    )


async def get_data(db: AsyncSession, dict_code: int) -> SysDictData:
    row = await db.scalar(select(SysDictData).where(SysDictData.dict_code == dict_code))
    if row is None:
        raise NotFoundException("字典数据不存在")
    return row


async def _assert_type_exists(db: AsyncSession, dict_type: str) -> None:
    exists = await db.scalar(select(SysDictType.dict_id).where(SysDictType.dict_type == dict_type).limit(1))
    if exists is None:
        raise BusinessException(f"字典类型不存在：{dict_type}")


async def create_data(db: AsyncSession, payload) -> SysDictData:
    await _assert_type_exists(db, payload.dict_type)
    row = SysDictData(
        dict_type=payload.dict_type,
        dict_label=payload.dict_label,
        dict_value=payload.dict_value,
        dict_sort=payload.dict_sort,
        tag_type=payload.tag_type,
        css_class=payload.css_class,
        is_default=payload.is_default,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def update_data(db: AsyncSession, payload) -> SysDictData:
    row = await get_data(db, payload.dict_code)
    if payload.dict_type != row.dict_type:
        await _assert_type_exists(db, payload.dict_type)

    row.dict_type = payload.dict_type
    row.dict_label = payload.dict_label
    row.dict_value = payload.dict_value
    row.dict_sort = payload.dict_sort
    row.tag_type = payload.tag_type
    row.css_class = payload.css_class
    row.is_default = payload.is_default
    row.status = payload.status
    row.remark = payload.remark
    await db.flush()
    await db.refresh(row)
    return row


async def delete_data(db: AsyncSession, dict_codes: list[int]) -> None:
    rows = list(await db.scalars(select(SysDictData).where(SysDictData.dict_code.in_(dict_codes))))
    for row in rows:
        row.del_flag = DelFlagEnum.DELETED
    await db.flush()
