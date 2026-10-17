"""Pure link tables.

Each row is the fact that two entities are related. These four tables carry no
audit columns and no behaviour, so they live together rather than being scattered
across the modules they connect.
"""

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SysUserRole(Base):
    """Which roles a user holds."""

    __tablename__ = "sys_user_role"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_role.role_id", ondelete="CASCADE"), primary_key=True
    )


class SysRoleMenu(Base):
    """Which menus (and therefore which buttons/permissions) a role grants."""

    __tablename__ = "sys_role_menu"

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_role.role_id", ondelete="CASCADE"), primary_key=True
    )
    menu_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_menu.menu_id", ondelete="CASCADE"), primary_key=True
    )


class SysUserPost(Base):
    """Which posts a user holds."""

    __tablename__ = "sys_user_post"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.user_id", ondelete="CASCADE"), primary_key=True
    )
    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_post.post_id", ondelete="CASCADE"), primary_key=True
    )


class SysRoleDept(Base):
    """Custom data scope (spec section 6.4, `data_scope = 2`).

    Only consulted when a role's `data_scope` is CUSTOM; the other four scopes are
    computed from the user's own department.
    """

    __tablename__ = "sys_role_dept"

    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_role.role_id", ondelete="CASCADE"), primary_key=True
    )
    dept_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_dept.dept_id", ondelete="CASCADE"), primary_key=True
    )
