"""服务监控接口。"""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.deps import require_perm
from app.core.response import success
from app.services import server_service

router = APIRouter(prefix="/server", tags=["monitor:server"])


@router.get(
    "", dependencies=[Depends(require_perm("monitor:server:list"))], summary="服务运行状态"
)
async def server_status() -> dict[str, Any]:
    return success(server_service.collect())
