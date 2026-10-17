"""Data-layer wiring: engine connectivity and the global soft-delete filter.

Behavioural proof that deleted rows are hidden needs a mapped entity; that arrives
with the models in Task 5. What is pinned here is the part that can already be
tested: the engine reaches the right database, and the filter really is attached.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.soft_delete import install_soft_delete_filter, is_soft_delete_filter_installed


async def test_engine_can_connect(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT VERSION()"))

    assert result.scalar().startswith("8.0.")


async def test_session_targets_the_test_database(db_session: AsyncSession) -> None:
    """A guard rail: no test may ever run against the development database."""
    result = await db_session.execute(text("SELECT DATABASE()"))

    assert result.scalar() == "enterprise_admin_test"


def test_soft_delete_filter_is_installed_on_import() -> None:
    assert is_soft_delete_filter_installed() is True


async def test_install_soft_delete_filter_is_idempotent(db_session: AsyncSession) -> None:
    install_soft_delete_filter(db_session)
    install_soft_delete_filter(db_session)

    assert is_soft_delete_filter_installed() is True
