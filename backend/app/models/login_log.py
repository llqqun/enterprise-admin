"""Login audit trail (`sys_login_log`).

Append-only. Both successes and failures are recorded, because the failure rows are
what make a lockout or a credential-stuffing attempt visible after the fact.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SysLoginLog(Base):
    __tablename__ = "sys_login_log"

    info_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="访问ID"
    )
    user_name: Mapped[str] = mapped_column(String(30), index=True, comment="登录账号")
    ipaddr: Mapped[str] = mapped_column(String(128), default="", comment="登录IP")
    login_location: Mapped[str] = mapped_column(
        String(255), default="", comment="登录地点"
    )
    browser: Mapped[str] = mapped_column(String(64), default="", comment="浏览器")
    os: Mapped[str] = mapped_column(String(64), default="", comment="操作系统")
    status: Mapped[str] = mapped_column(
        String(1), default="0", comment="登录状态(0成功 1失败)"
    )
    msg: Mapped[str] = mapped_column(String(255), default="", comment="提示消息")
    login_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, comment="登录时间"
    )

    def __repr__(self) -> str:
        return f"<SysLoginLog {self.user_name!r} status={self.status}>"
