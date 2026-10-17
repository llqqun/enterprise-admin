"""Data-layer wiring: engine connectivity, schema shape and the soft-delete filter."""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum
from app.db.soft_delete import (
    include_deleted,
    install_soft_delete_filter,
    is_soft_delete_filter_installed,
)
from app.models.dept import SysDept
from app.models.user import SysUser

CORE_TABLES = {
    "sys_dept",
    "sys_post",
    "sys_user",
    "sys_role",
    "sys_menu",
    "sys_user_role",
    "sys_role_menu",
    "sys_user_post",
    "sys_role_dept",
    "sys_user_token",
    "sys_login_log",
}


# ---------------------------------------------------------------------------
# Engine / session wiring
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


async def test_core_tables_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        )
    )
    present = {row[0] for row in result}

    assert CORE_TABLES <= present


async def test_tables_use_utf8mb4(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT DISTINCT table_collation FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name LIKE 'sys_%'"
        )
    )
    collations = {row[0] for row in result}

    assert collations == {"utf8mb4_0900_ai_ci"}


async def test_user_name_has_no_unique_index(db_session: AsyncSession) -> None:
    """Logical delete requires a non-unique index on the business key.

    A UNIQUE index would make it impossible to re-create a user with the same
    account name after the previous one was logically deleted.
    """
    result = await db_session.execute(
        text(
            "SELECT index_name, non_unique FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() AND table_name = 'sys_user' "
            "AND column_name = 'user_name'"
        )
    )
    rows = list(result)

    assert rows, "expected an index on sys_user.user_name"
    assert all(row[1] == 1 for row in rows), "user_name must not be UNIQUE"


async def test_deleted_rows_are_hidden_from_queries(db_session: AsyncSession) -> None:
    db_session.add(
        SysDept(
            dept_id=9001,
            parent_id=0,
            ancestors="0",
            dept_name="已删除部门",
            order_num=1,
            del_flag=DelFlagEnum.DELETED,
        )
    )
    await db_session.flush()

    found = await db_session.scalar(select(SysDept).where(SysDept.dept_id == 9001))

    assert found is None


async def test_include_deleted_reveals_hidden_rows(db_session: AsyncSession) -> None:
    db_session.add(
        SysDept(
            dept_id=9002,
            parent_id=0,
            ancestors="0",
            dept_name="已删除部门",
            order_num=1,
            del_flag=DelFlagEnum.DELETED,
        )
    )
    await db_session.flush()

    include_deleted(db_session)
    found = await db_session.scalar(select(SysDept).where(SysDept.dept_id == 9002))

    assert found is not None
    assert found.dept_name == "已删除部门"


async def test_deleted_user_name_can_be_reused(db_session: AsyncSession) -> None:
    """A logically deleted account must not block re-creating the same name."""
    db_session.add(
        SysUser(
            user_name="dup_user",
            nick_name="旧账号",
            password="x",
            del_flag=DelFlagEnum.DELETED,
        )
    )
    await db_session.flush()

    db_session.add(SysUser(user_name="dup_user", nick_name="新账号", password="y"))
    await db_session.flush()  # must not raise IntegrityError

    visible = await db_session.scalars(select(SysUser).where(SysUser.user_name == "dup_user"))
    assert len(visible.all()) == 1

    total = await db_session.scalar(
        select(func.count()).select_from(SysUser).where(SysUser.user_name == "dup_user")
    )
    assert total == 1  # the deleted row is filtered out of the count too
