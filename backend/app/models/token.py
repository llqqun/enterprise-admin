"""Persisted token records (`sys_user_token`).

A purely stateless JWT cannot be revoked, so "log out", "force logout" and the
online-user list all need a server-side record keyed by `jti`. The cost is one
indexed lookup per authenticated request; the benefit is that logging out actually
means something.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SysUserToken(Base):
    __tablename__ = "sys_user_token"

    token_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="令牌记录ID"
    )
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="用户ID")
    access_jti: Mapped[str] = mapped_column(
        String(64), index=True, comment="访问令牌唯一标识"
    )
    access_expire: Mapped[datetime] = mapped_column(DateTime, comment="访问令牌过期时间")
    refresh_jti: Mapped[str] = mapped_column(
        String(64), index=True, comment="刷新令牌唯一标识"
    )
    refresh_expire: Mapped[datetime] = mapped_column(DateTime, comment="刷新令牌过期时间")
    login_ip: Mapped[str] = mapped_column(String(128), default="", comment="登录IP")
    browser: Mapped[str] = mapped_column(String(64), default="", comment="浏览器")
    os: Mapped[str] = mapped_column(String(64), default="", comment="操作系统")
    login_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="登录时间"
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), comment="是否已撤销"
    )

    def __repr__(self) -> str:
        return f"<SysUserToken user={self.user_id} revoked={self.revoked}>"
