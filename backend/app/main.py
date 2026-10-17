"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import (
    BusinessException,
    ForbiddenException,
    NotFoundException,
    register_exception_handlers,
)
from app.core.logging import setup_logging
from app.middlewares.request_id import RequestIdMiddleware


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

    @app.get("/health", tags=["system"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": settings.APP_VERSION}

    if settings.DEBUG:
        _register_debug_routes(app)

    return app


app = create_app()
