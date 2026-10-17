"""Shared pytest fixtures.

Async tests need no decorator: `pytest.ini` sets `asyncio_mode = auto` and
`pythonpath = .`, so `app` is importable and every `async def test_*` runs.

Every test that touches the database runs against `enterprise_admin_test`, inside
a transaction that is rolled back — the development database is never touched.
"""

from collections.abc import AsyncGenerator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.db.session import get_db
from app.db.soft_delete import install_soft_delete_filter
from app.main import create_app

TEST_DB = "enterprise_admin_test"


def _test_settings() -> Settings:
    """Application settings pointed at the test database."""
    return get_settings().model_copy(update={"MYSQL_DB": TEST_DB})


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> None:
    """Bring the test schema to head once per session.

    Deliberately synchronous: alembic's async `env.py` calls `asyncio.run()`, which
    cannot run inside a live event loop, and this fixture executes before the
    async fixtures that own one. `upgrade head` is a no-op when already current.
    """
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", (BACKEND_DIR / "alembic").as_posix())
    config.attributes["sqlalchemy_url"] = _test_settings().database_url
    command.upgrade(config, "head")


@pytest.fixture()
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """A throwaway engine bound to the test database.

    Created per test with `NullPool`: pytest-asyncio gives every test its own event
    loop, and a pooled connection created under one loop cannot be reused under
    the next.
    """
    test_engine = create_async_engine(_test_settings().database_url, poolclass=NullPool)
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest.fixture()
async def db_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """A session whose work is always rolled back.

    The outer transaction is opened on the connection; the session joins it via
    savepoints, so code under test can `commit()` freely without escaping the
    rollback.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        install_soft_delete_filter(session)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired straight to the ASGI app (no network, no server).

    `raise_app_exceptions=False` mirrors what a real server does: Starlette's
    ServerErrorMiddleware renders the 500 response and *then* re-raises so the
    server can log it. A real client sees the response, so the test client must
    too — otherwise the "unhandled exception" tests could never observe the
    handler's output.

    `get_db` is overridden so requests share `db_session`, and therefore share its
    rollback.
    """
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
