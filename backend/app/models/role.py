"""Roles (`sys_role`) and the two things a role decides: menus and data scope."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DataScopeEnum, StatusEnum
from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.dept import SysDept
    from app.models.menu import SysMenu


class SysRole(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_role"

    role_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="角色ID"
    )
    role_name: Mapped[str] = mapped_column(String(30), comment="角色名称")
    # The key is the string the code compares against (e.g. "admin"). Indexed but
    # not UNIQUE, for the same logical-delete reason as sys_user.user_name.
    role_key: Mapped[str] = mapped_column(String(100), index=True, comment="角色权限字符串")
    role_sort: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="显示顺序"
    )
    data_scope: Mapped[str] = mapped_column(
        String(1),
        default=str(int(DataScopeEnum.ALL)),
        server_default=str(int(DataScopeEnum.ALL)),
        comment="数据范围(1全部 2自定义 3本部门 4本部门及以下 5仅本人)",
    )
    menu_check_strictly: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("1"),
        comment="菜单树选择项是否父子联动",
    )
    dept_check_strictly: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("1"),
        comment="部门树选择项是否父子联动",
    )
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="角色状态(0正常 1停用)",
    )

    # Both are needed on the auth path: menus produce the permission codes, depts
    # produce the custom data scope.
    menus: Mapped[list["SysMenu"]] = relationship(
        "SysMenu", secondary="sys_role_menu", lazy="selectin"
    )
    depts: Mapped[list["SysDept"]] = relationship(
        "SysDept", secondary="sys_role_dept", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SysRole {self.role_id} {self.role_key!r}>"
