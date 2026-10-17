"""User accounts (`sys_user`)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import StatusEnum
from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:  # imported for type checkers only; SQLAlchemy resolves the strings
    from app.models.dept import SysDept
    from app.models.post import SysPost
    from app.models.role import SysRole


class SysUser(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_user"

    user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="用户ID"
    )
    dept_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sys_dept.dept_id"), default=None, index=True, comment="部门ID"
    )
    # Indexed but deliberately NOT unique: a logically deleted account must not
    # block re-creating the same name. See
    # tests/test_models_migration.py::test_user_name_has_no_unique_index.
    user_name: Mapped[str] = mapped_column(String(30), index=True, comment="用户账号")
    nick_name: Mapped[str] = mapped_column(String(30), comment="用户昵称")
    user_type: Mapped[str] = mapped_column(
        String(2), default="00", server_default="00", comment="用户类型(00系统用户)"
    )
    email: Mapped[str | None] = mapped_column(String(50), default=None, comment="邮箱")
    phonenumber: Mapped[str | None] = mapped_column(String(11), default=None, comment="手机号")
    sex: Mapped[str] = mapped_column(
        String(1), default="2", server_default="2", comment="性别(0男 1女 2未知)"
    )
    avatar: Mapped[str | None] = mapped_column(String(255), default=None, comment="头像地址")
    password: Mapped[str] = mapped_column(String(100), comment="bcrypt 哈希")
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="账号状态(0正常 1停用)",
    )
    login_ip: Mapped[str | None] = mapped_column(String(128), default=None, comment="最后登录IP")
    login_date: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, comment="最后登录时间"
    )
    pwd_update_date: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, comment="密码最后更新时间"
    )

    # Eager by design: the auth path needs dept and roles on every request, and an
    # implicit lazy load would raise MissingGreenlet under async. `posts` is eager
    # because the user list renders post names.
    dept: Mapped["SysDept | None"] = relationship("SysDept", lazy="joined")
    roles: Mapped[list["SysRole"]] = relationship(
        "SysRole", secondary="sys_user_role", lazy="selectin"
    )
    posts: Mapped[list["SysPost"]] = relationship(
        "SysPost", secondary="sys_user_post", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SysUser {self.user_id} {self.user_name!r}>"

    @property
    def is_active(self) -> bool:
        return self.status == StatusEnum.NORMAL


__all__ = ["SysUser"]
