"""字典接口。

路径里的字面量段（`/type`、`/data/type/{dict_type}`）必须声明在 `/{x_id}` 之前。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.dict import (
    DictDataCreate,
    DictDataOut,
    DictDataUpdate,
    DictTypeCreate,
    DictTypeOut,
    DictTypeUpdate,
)
from app.services import dict_service

router = APIRouter(prefix="/dict", tags=["system:dict"])


def _parse_ids(ids: str) -> list[int]:
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


# ---------------------------------------------------------------------------
# 类型
# ---------------------------------------------------------------------------


@router.get("/type", dependencies=[Depends(require_perm("system:dict:list"))], summary="字典类型列表")
async def list_types(
    dict_name: str | None = None,
    dict_type: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await dict_service.list_types(
        db, params, dict_name=dict_name, dict_type=dict_type, status=status
    )
    return page([DictTypeOut.model_validate(row).model_dump() for row in rows], total)


@router.get(
    "/type/{dict_id}", dependencies=[Depends(require_perm("system:dict:query"))], summary="字典类型详情"
)
async def get_type(dict_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(DictTypeOut.model_validate(await dict_service.get_type(db, dict_id)).model_dump())


@router.post("/type", dependencies=[Depends(require_perm("system:dict:add"))], summary="新增字典类型")
async def create_type(payload: DictTypeCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await dict_service.create_type(db, payload)
    return success(DictTypeOut.model_validate(row).model_dump(), msg="新增成功")


@router.put("/type", dependencies=[Depends(require_perm("system:dict:edit"))], summary="修改字典类型")
async def update_type(payload: DictTypeUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await dict_service.update_type(db, payload)
    return success(DictTypeOut.model_validate(row).model_dump(), msg="修改成功")


@router.delete(
    "/type/{ids}", dependencies=[Depends(require_perm("system:dict:remove"))], summary="删除字典类型"
)
async def delete_types(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await dict_service.delete_types(db, _parse_ids(ids))
    return success(msg="删除成功")


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------


@router.get("/data", dependencies=[Depends(require_perm("system:dict:list"))], summary="字典数据列表")
async def list_data(
    dict_type: str | None = None,
    dict_label: str | None = None,
    status: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await dict_service.list_data(
        db, params, dict_type=dict_type, dict_label=dict_label, status=status
    )
    return page([DictDataOut.model_validate(row).model_dump() for row in rows], total)


@router.get(
    "/data/type/{dict_type}", summary="按类型取启用中的字典项（前端渲染标签用）"
)
async def data_by_type(dict_type: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """**只要求登录，不要求 `system:dict:list`。**

    每个页面都可能要渲染一个状态标签；如果这里也要求字典管理权限，那么一个只会看订单的人
    就没法把 `status=0` 显示成「正常」。字典是公共词汇表，不是敏感数据。
    """
    rows = await dict_service.data_by_type(db, dict_type)
    return success([DictDataOut.model_validate(row).model_dump() for row in rows])


@router.get(
    "/data/{dict_code}", dependencies=[Depends(require_perm("system:dict:query"))], summary="字典数据详情"
)
async def get_data(dict_code: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(DictDataOut.model_validate(await dict_service.get_data(db, dict_code)).model_dump())


@router.post("/data", dependencies=[Depends(require_perm("system:dict:add"))], summary="新增字典数据")
async def create_data(payload: DictDataCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await dict_service.create_data(db, payload)
    return success(DictDataOut.model_validate(row).model_dump(), msg="新增成功")


@router.put("/data", dependencies=[Depends(require_perm("system:dict:edit"))], summary="修改字典数据")
async def update_data(payload: DictDataUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    row = await dict_service.update_data(db, payload)
    return success(DictDataOut.model_validate(row).model_dump(), msg="修改成功")


@router.delete(
    "/data/{ids}", dependencies=[Depends(require_perm("system:dict:remove"))], summary="删除字典数据"
)
async def delete_data(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await dict_service.delete_data(db, _parse_ids(ids))
    return success(msg="删除成功")
