"""FastAPI application factory."""

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.deps import CurrentUser, get_current_user, require_perm
from app.core.exceptions import (
    BusinessException,
    ForbiddenException,
    NotFoundException,
    register_exception_handlers,
)
from app.core.logging import setup_logging
from app.core.response import success
from app.middlewares.request_id import RequestIdMiddleware

#: The permission code the debug-only permission endpoint demands. Shared with the
#: test suite so the fixture and the route cannot drift apart.
DEBUG_TEST_PERM = "system:test:view"


def _register_debug_routes(app: FastAPI) -> None:
    """Endpoints that exist only while DEBUG is on.

    The exception handlers are the production code under test in
    `tests/test_response_and_errors.py`; these routes are how the tests reach them
    over real HTTP instead of calling the handlers directly.
    """

    @app.get("/__test__/boom-business", include_in_schema=False)
    async def _boom_business() -> None:
        raise BusinessException("库存不足")

    @app.get("/__test__/boom-forbidden", include_in_schema=False)
    async def _boom_forbidden() -> None:
        raise ForbiddenException("没有访问权限")

    @app.get("/__test__/boom-not-found", include_in_schema=False)
    async def _boom_not_found() -> None:
        raise NotFoundException("资源不存在")

    @app.get("/__test__/boom-unhandled", include_in_schema=False)
    async def _boom_unhandled() -> None:
        # The message deliberately carries everything a 500 response must never echo
        # back: the exception text, SQL, a password and a DSN.
        raise RuntimeError(
            "kaboom: SELECT * FROM sys_user WHERE password='Admin@123456' "
            "dsn=mysql+asyncmy://root:Admin@123456@127.0.0.1:3306/enterprise_admin"
        )

    @app.get("/__test__/validate", include_in_schema=False)
    async def _validate(q: int) -> dict[str, int]:
        return {"q": q}

    @app.get("/__test__/need-perm", include_in_schema=False)
    async def _need_perm(
        current: CurrentUser = Depends(require_perm(DEBUG_TEST_PERM)),
    ) -> dict[str, Any]:
        return {"user_id": current.user_id, "perm": DEBUG_TEST_PERM}

    @app.get("/__test__/scope", include_in_schema=False)
    async def _scope(current: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
        """Expose the caller's resolved data scope.

        Reading it back over real HTTP is the only way to prove the wiring in
        `get_current_user` works. The profile response deliberately does not carry
        it: a data scope is a server-side query concern, not client state.
        """
        scope = current.data_scope
        return success(
            {
                "unrestricted": scope.unrestricted,
                "grants_nothing": scope.grants_nothing,
                "rules": [
                    {
                        "mode": rule.mode,
                        "dept_id": rule.dept_id,
                        "custom_dept_ids": sorted(rule.custom_dept_ids),
                    }
                    for rule in scope.rules
                ],
            }
        )


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    for directory in (settings.UPLOAD_DIR, settings.LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs" if settings.DOCS_ENABLED else None,
        redoc_url="/redoc" if settings.DOCS_ENABLED else None,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last so it is the outermost user middleware: the correlation id is
    # assigned before anything else can log or fail.
    app.add_middleware(RequestIdMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router)

    @app.get("/health", tags=["system"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.APP_VERSION}

    if settings.DEBUG:
        _register_debug_routes(app)

    return app


app = create_app()
