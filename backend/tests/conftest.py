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

from app.core.cache import cache
from app.core.config import BACKEND_DIR, Settings, get_settings
from app.core.constants import DelFlagEnum, StatusEnum
from app.core.security import hash_password
from app.db.session import get_db
from app.db.soft_delete import install_soft_delete_filter
from app.main import DEBUG_TEST_PERM, create_app
from app.models.associations import SysRoleMenu, SysUserRole
from app.models.menu import SysMenu
from app.models.role import SysRole
from app.models.user import SysUser

TEST_DB = "enterprise_admin_test"
TEST_PERM = DEBUG_TEST_PERM


def _test_settings() -> Settings:
    """Application settings pointed at the test database."""
    return get_settings().model_copy(update={"MYSQL_DB": TEST_DB})


@pytest.fixture(autouse=True)
async def _isolated_cache() -> AsyncGenerator[None, None]:
    """Empty the process-wide cache around every test.

    `cache` is a module-level singleton by design, so without this a lockout counter
    or a captcha answer left behind by one test silently changes the behaviour of
    the next one. Clearing on both sides also keeps a failing test from poisoning
    whatever runs after it.
    """
    await cache.clear()
    yield
    await cache.clear()


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


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------

#: The password every seeded test account uses.
SEED_PASSWORD = "Admin@123456"


async def _make_user(db_session: AsyncSession, user_name: str, **overrides: object) -> SysUser:
    fields: dict[str, object] = {
        "nick_name": user_name,
        "password": hash_password(SEED_PASSWORD),
        "status": StatusEnum.NORMAL,
    }
    fields.update(overrides)
    user = SysUser(user_name=user_name, **fields)  # type: ignore[arg-type]
    db_session.add(user)
    await db_session.flush()
    return user


async def _grant_role(db_session: AsyncSession, user: SysUser, role: SysRole) -> None:
    """Link a user to a role by inserting the association row.

    Deliberately not `user.roles.append(...)`: on an already-flushed instance the
    collection was never loaded by a query, so touching it triggers a lazy load —
    which raises MissingGreenlet under async. Loading the user through a `select()`
    first would also work; writing the link row says what is actually happening.
    """
    db_session.add(SysUserRole(user_id=user.user_id, role_id=role.role_id))
    await db_session.flush()


async def _grant_menu(db_session: AsyncSession, role: SysRole, menu: SysMenu) -> None:
    """Same reasoning as `_grant_role`."""
    db_session.add(SysRoleMenu(role_id=role.role_id, menu_id=menu.menu_id))
    await db_session.flush()


@pytest.fixture()
async def admin_role(db_session: AsyncSession) -> SysRole:
    """The superuser role: `is_admin` is decided by this role key alone."""
    role = SysRole(
        role_name="超级管理员",
        role_key="admin",
        role_sort=1,
        data_scope="1",
        status=StatusEnum.NORMAL,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest.fixture()
async def staff_role(db_session: AsyncSession) -> SysRole:
    role = SysRole(
        role_name="普通员工",
        role_key="staff",
        role_sort=9,
        data_scope="5",
        status=StatusEnum.NORMAL,
    )
    db_session.add(role)
    await db_session.flush()
    return role


@pytest.fixture()
async def admin_user(db_session: AsyncSession, admin_role: SysRole) -> SysUser:
    """An active account named `admin` holding the superuser role."""
    user = await _make_user(db_session, "admin")
    await _grant_role(db_session, user, admin_role)
    return user


@pytest.fixture()
async def normal_user(db_session: AsyncSession, staff_role: SysRole) -> SysUser:
    """An active, non-superuser account with no permissions at all."""
    user = await _make_user(db_session, "staff")
    await _grant_role(db_session, user, staff_role)
    return user


@pytest.fixture()
async def permitted_user(db_session: AsyncSession, staff_role: SysRole) -> SysUser:
    """A non-superuser whose role grants exactly the `system:test:view` button.

    Exists so a 403 can be told apart from "the permission check always fails".
    """
    menu = SysMenu(
        menu_name="测试按钮",
        parent_id=0,
        order_num=1,
        menu_type="F",
        perms=TEST_PERM,
        status=StatusEnum.NORMAL,
    )
    db_session.add(menu)
    await db_session.flush()

    role = SysRole(
        role_name="受限角色",
        role_key="limited",
        role_sort=5,
        data_scope="5",
        status=StatusEnum.NORMAL,
    )
    db_session.add(role)
    await db_session.flush()
    await _grant_menu(db_session, role, menu)

    user = await _make_user(db_session, "limited")
    await _grant_role(db_session, user, role)
    return user


@pytest.fixture()
async def disabled_user(db_session: AsyncSession) -> SysUser:
    return await _make_user(db_session, "disabled", status=StatusEnum.DISABLED)


@pytest.fixture()
async def deleted_admin_user(db_session: AsyncSession) -> SysUser:
    """The same account name, logically deleted."""
    return await _make_user(db_session, "admin", del_flag=DelFlagEnum.DELETED)
