"""Async engine, session factory and the request-scoped session dependency."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.soft_delete import install_soft_delete_filter

settings = get_settings()

# Creating an engine does not open a connection, so importing this module works
# even when MySQL is down; the failure surfaces at first use with a clear error.
engine = create_async_engine(
    settings.database_url,
    echo=False,
    # Recycles connections before MySQL's 8-hour wait_timeout can kill them, and
    # verifies a pooled connection before handing it out.
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """One session per request.

    Commits when the handler returns normally, rolls back on any exception, and
    always closes. Handlers may still commit earlier if they need to.
    """
    session = AsyncSessionLocal()
    install_soft_delete_filter(session)
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
