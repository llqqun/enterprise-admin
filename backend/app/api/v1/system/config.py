"""参数配置接口。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.response import PageParams, page, success
from app.db.session import get_db
from app.schemas.config import ConfigCreate, ConfigOut, ConfigUpdate
from app.services import config_service

router = APIRouter(prefix="/config", tags=["system:config"])


def _parse_ids(ids: str) -> list[int]:
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if not parts or not all(part.isdigit() for part in parts):
        raise HTTPException(status_code=422, detail="ID 列表格式不正确")
    return [int(part) for part in parts]


@router.get("", dependencies=[Depends(require_perm("system:config:list"))], summary="参数列表")
async def list_configs(
    config_name: str | None = None,
    config_key: str | None = None,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    rows, total = await config_service.list_configs(
        db, params, config_name=config_name, config_key=config_key
    )
    return page([ConfigOut.model_validate(row).model_dump() for row in rows], total)


@router.get("/configKey/{config_key}", summary="按键取参数值（前端/业务读取用）")
async def get_value(config_key: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """只要求登录：读一个开关的值不该需要「参数管理」权限。"""
    return success(await config_service.get_value(db, config_key))


@router.get(
    "/{config_id}", dependencies=[Depends(require_perm("system:config:query"))], summary="参数详情"
)
async def get_config(config_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(ConfigOut.model_validate(await config_service.get_config(db, config_id)).model_dump())


@router.post("", dependencies=[Depends(require_perm("system:config:add"))], summary="新增参数")
async def create_config(payload: ConfigCreate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(ConfigOut.model_validate(await config_service.create_config(db, payload)).model_dump(), msg="新增成功")


@router.put("", dependencies=[Depends(require_perm("system:config:edit"))], summary="修改参数")
async def update_config(payload: ConfigUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return success(ConfigOut.model_validate(await config_service.update_config(db, payload)).model_dump(), msg="修改成功")


@router.delete(
    "/{ids}", dependencies=[Depends(require_perm("system:config:remove"))], summary="删除参数"
)
async def delete_configs(ids: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    await config_service.delete_configs(db, _parse_ids(ids))
    return success(msg="删除成功")
