"""Application exception hierarchy and the global handlers that render it.

Every error leaves the process through `{"code", "msg", "data"}`. Internal
detail (stack traces, SQL, DSNs, credentials) is logged, never returned.
"""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException

GENERIC_ERROR_MSG = "系统内部错误，请稍后重试"


class AppException(Exception):
    """Base class for every error this application raises deliberately.

    `code` is the business code carried in the response body; `http_status` is
    what the transport reports. They coincide by default and are separate so a
    future business code can differ from its HTTP status without reshaping the
    handler.
    """

    def __init__(self, code: int, msg: str, http_status: int = 400) -> None:
        self.code = code
        self.msg = msg
        self.http_status = http_status
        super().__init__(msg)


class BusinessException(AppException):
    """A business rule rejected the request."""

    def __init__(self, msg: str, code: int = 400) -> None:
        super().__init__(code=code, msg=msg, http_status=400)


class UnauthorizedException(AppException):
    """Missing, malformed, expired or revoked credentials."""

    def __init__(self, msg: str = "登录状态已失效，请重新登录", code: int = 401) -> None:
        super().__init__(code=code, msg=msg, http_status=401)


class ForbiddenException(AppException):
    """Authenticated, but not allowed."""

    def __init__(self, msg: str = "没有操作权限", code: int = 403) -> None:
        super().__init__(code=code, msg=msg, http_status=403)


class NotFoundException(AppException):
    """The addressed resource does not exist."""

    def __init__(self, msg: str = "资源不存在", code: int = 404) -> None:
        super().__init__(code=code, msg=msg, http_status=404)


class ValidationException(AppException):
    """A domain-level validation failure (as opposed to a schema failure)."""

    def __init__(self, msg: str = "参数校验失败", code: int = 422) -> None:
        super().__init__(code=code, msg=msg, http_status=422)


_LOCATION_PREFIXES = {"body", "query", "path", "header", "cookie"}


def _field_path(loc: Sequence[Any]) -> str:
    """Turn a pydantic error location into a dotted field path.

    `("query", "q")` -> `"q"`; `("body", "user", "name")` -> `"user.name"`.
    """
    parts = list(loc)
    if parts and str(parts[0]) in _LOCATION_PREFIXES:
        parts = parts[1:]
    return ".".join(str(part) for part in parts)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "msg": exc.msg, "data": None},
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"field": _field_path(error.get("loc", ())), "msg": error.get("msg", "")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"code": 422, "msg": "参数校验失败", "data": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "msg": str(exc.detail), "data": None},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        # Full detail goes to the log (with the request id so it can be correlated);
        # the client only learns that something went wrong.
        logger.opt(exception=exc).error(
            "Unhandled exception [request_id={}] {} {}",
            request_id,
            request.method,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": GENERIC_ERROR_MSG, "data": None},
        )
