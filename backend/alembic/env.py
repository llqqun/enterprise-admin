"""Alembic environment (async).

The target URL is resolved in this order:

1. `config.attributes["sqlalchemy_url"]` — set programmatically by the test suite
   so migrations run against `enterprise_admin_test`;
2. `-x db=<name>` — overrides only the database name, so a second database can be
   migrated without editing `.env`;
3. application settings.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base

# Import side effect: registers every model on Base.metadata so autogenerate sees
# them. Never remove, even while it looks unused.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    override = config.attributes.get("sqlalchemy_url")
    if override:
        return str(override)

    settings = get_settings()
    db_name = context.get_x_argument(as_dictionary=True).get("db")
    if db_name:
        settings = settings.model_copy(update={"MYSQL_DB": db_name})
    return settings.database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (``alembic upgrade --sql``)."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Without this, changing a column's type or length produces an empty
        # migration and the drift goes unnoticed.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
