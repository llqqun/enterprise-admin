"""操作日志：写入装饰器与查询。

**为什么是装饰器而不是中间件**：中间件只看得到 URL 和状态码，看不到「这次调用是新增用户还是
删除角色」——而后者才是审计要回答的问题。代价是每个要记的接口都得显式挂上 `@oper_log`，
这是刻意的：审计范围应当是被决定过的，而不是「所有请求都记」。

**参数脱敏是硬要求**：`POST /system/user` 的请求体里有明文密码。把请求体原样写进日志，
等于把密码以明文永久留在数据库里 —— 一条审计日志变成了凭据泄漏源。
"""

import functools
import inspect
import json
import time
from typing import Any, Callable

from fastapi import Request
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.exceptions import BusinessException
from app.core.response import PageParams
from app.models.oper_log import SysOperLog

#: 这些键的值一律替换掉，且**不区分大小写**（`Password` / `newPassword` 都要覆盖）。
SENSITIVE_KEYS = ("password", "pwd", "passwd", "secret", "token")
MASK = "***"
MAX_TEXT = 2000


def _sanitize(value: Any) -> Any:
    """递归地把敏感字段替换成 `***`。

    逐层递归而不是只看顶层：请求体常常是 `{"user": {...}, "role_ids": [...]}` 这种结构，
    只处理第一层会让嵌套的密码漏出去。
    """
    if isinstance(value, dict):
        return {
            key: (
                MASK
                if isinstance(key, str) and any(word in key.lower() for word in SENSITIVE_KEYS)
                else _sanitize(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _payload_text(body: bytes) -> str | None:
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        # 不是 JSON（表单、文件）时宁可不记，也不要把原始字节塞进日志。
        return None
    return json.dumps(_sanitize(parsed), ensure_ascii=False)[:MAX_TEXT]


def _arg_of_type(func: Callable[..., Any], args: tuple, kwargs: dict, wanted: type) -> Any:
    """按**类型**而不是按参数名去找，这样接口把参数叫 `db` 还是 `session` 都无所谓。"""
    try:
        bound = inspect.signature(func).bind_partial(*args, **kwargs)
    except TypeError:
        return None
    for value in bound.arguments.values():
        if isinstance(value, wanted):
            return value
    return None


def oper_log(title: str, business_type: int) -> Callable[..., Any]:
    """记录一次业务操作的审计日志。

    写日志本身**绝不**能让业务失败：任何记录环节的异常都被吞掉并降级为一条 warning。
    审计很重要，但不值得用「记不上就返回 500」去换。
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            request = _arg_of_type(func, args, kwargs, Request)
            db = _arg_of_type(func, args, kwargs, AsyncSession)
            # 先看签名里有没有 `CurrentUser`；没有就看 `get_current_user` 挂在
            # `request.state` 上的那一份（多数写接口只在 `dependencies` 里用权限码，
            # 签名里并不声明当前用户）。
            current = _arg_of_type(func, args, kwargs, CurrentUser) or (
                getattr(request.state, "current_user", None) if request is not None else None
            )

            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                await _safe_record(
                    db,
                    request=request,
                    current=current,
                    title=title,
                    business_type=business_type,
                    cost_ms=int((time.perf_counter() - started) * 1000),
                    status="1",
                    error_msg=str(exc)[:MAX_TEXT],
                    json_result=None,
                )
                raise

            await _safe_record(
                db,
                request=request,
                current=current,
                title=title,
                business_type=business_type,
                cost_ms=int((time.perf_counter() - started) * 1000),
                status="0",
                error_msg=None,
                json_result=None,
            )
            return result

        return wrapper

    return decorator


async def _safe_record(
    db: AsyncSession | None,
    *,
    request: Request | None,
    current: CurrentUser | None,
    title: str,
    business_type: int,
    cost_ms: int,
    status: str,
    error_msg: str | None,
    json_result: str | None,
) -> None:
    """写一行日志；任何失败都只留一个 warning。

    注意：这里与业务**共用同一个会话**。代价是业务抛异常导致事务回滚时，那条失败日志会跟着回滚
    （MySQL 没有自治事务）。换成独立会话可以保住它，但会让测试里的写入逃出测试事务、污染数据库，
    而失败原因本身已经在前端提示与 loguru 里有一份。这个取舍写在 `docs/P1决策记录.md`。
    """
    if db is None:
        return
    try:
        body = b""
        if request is not None and request.method in ("POST", "PUT", "PATCH"):
            # Starlette 会缓存已读取的 body，所以这里拿到的是 FastAPI 解析时读过的那份。
            body = await request.body()

        db.add(
            SysOperLog(
                title=title,
                business_type=business_type,
                method=getattr(request.scope.get("endpoint"), "__qualname__", "") if request else "",
                request_method=request.method if request else "",
                oper_name=current.user_name if current else "",
                dept_name=str(current.dept_id) if current and current.dept_id is not None else "",
                oper_url=request.url.path if request else "",
                oper_ip=(request.client.host if request and request.client else "")[:128],
                oper_location="",
                oper_param=_payload_text(body),
                json_result=json_result,
                status=status,
                error_msg=error_msg,
                cost_ms=cost_ms,
            )
        )
        await db.flush()
    except Exception as exc:  # 审计写失败不允许影响业务
        logger.warning("oper log not recorded title={} err={}", title, exc)


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


async def list_oper_logs(
    db: AsyncSession,
    params: PageParams,
    *,
    title: str | None = None,
    oper_name: str | None = None,
    status: str | None = None,
) -> tuple[list[SysOperLog], int]:
    statement = select(SysOperLog)
    if title:
        statement = statement.where(SysOperLog.title.contains(title))
    if oper_name:
        statement = statement.where(SysOperLog.oper_name.contains(oper_name))
    if status:
        statement = statement.where(SysOperLog.status == status)

    total = int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    offset = (params.page_num - 1) * params.page_size
    rows = list(
        await db.scalars(
            statement.order_by(SysOperLog.oper_time.desc(), SysOperLog.oper_id.desc())
            .limit(params.page_size)
            .offset(offset)
        )
    )
    return rows, total


async def delete_oper_logs(db: AsyncSession, oper_ids: list[int], current: CurrentUser) -> None:
    """批量删除。

    审计日志原则上应当只增不删；这里保留删除能力是因为设计文档 §8.3 列出了它，但把它挡在
    单独的权限码之后，并且**先写一条清理日志**再删 —— 让「删日志」这个动作本身也留痕。
    """
    from sqlalchemy import delete

    if not oper_ids:
        return

    await db.execute(delete(SysOperLog).where(SysOperLog.oper_id.in_(oper_ids)))
    # 先删再写留痕：反过来写的话，这条标记自己也会被同一次删除清掉。
    await db.execute(
        SysOperLog.__table__.insert().values(
            title="操作日志",
            business_type=3,
            method="delete_oper_logs",
            request_method="DELETE",
            oper_name=current.user_name,
            dept_name="",
            oper_url="/api/v1/monitor/operlog",
            oper_ip="",
            oper_location="",
            oper_param=f"删除日志 id={oper_ids}",
            status="0",
            cost_ms=0,
        )
    )
    await db.flush()


async def clean_oper_logs(db: AsyncSession, current: CurrentUser) -> None:
    from sqlalchemy import delete

    await db.execute(delete(SysOperLog))
    # 同上：先清空，再留下「谁清空过」这一条。
    await db.execute(
        SysOperLog.__table__.insert().values(
            title="操作日志",
            business_type=9,
            method="clean_oper_logs",
            request_method="DELETE",
            oper_name=current.user_name,
            dept_name="",
            oper_url="/api/v1/monitor/operlog/clean",
            oper_ip="",
            oper_location="",
            oper_param="清空操作日志",
            status="0",
            cost_ms=0,
        )
    )
    await db.flush()
