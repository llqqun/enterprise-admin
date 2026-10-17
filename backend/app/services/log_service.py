"""Login audit persistence."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_log import SysLoginLog

LOGIN_SUCCESS = "0"
LOGIN_FAILURE = "1"


async def record_login_log(
    db: AsyncSession,
    *,
    user_name: str,
    status: str,
    msg: str,
    ipaddr: str = "",
    browser: str = "",
    os: str = "",
) -> None:
    """Append one audit row.

    Every column is truncated to its schema width so an over-long user agent cannot
    turn an audit write into a failed login. The insert is flushed (not committed)
    so it participates in the caller's transaction.
    """
    db.add(
        SysLoginLog(
            user_name=user_name[:30],
            ipaddr=ipaddr[:128],
            login_location="",
            browser=browser[:64],
            os=os[:64],
            status=status,
            msg=msg[:255],
        )
    )
    await db.flush()
