"""Menu / permission tree (`sys_menu`).

One table holds three kinds of node, distinguished by `menu_type`:

* ``M`` directory — a grouping node, renders as a submenu, has no page
* ``C`` menu      — an actual page, drives a dynamic route
* ``F`` button    — no route at all; it exists only to carry a `perms` code

That is why the table carries both routing columns (`path`, `component`) and the
authorisation column (`perms`).
"""

from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import MenuTypeEnum, StatusEnum
from app.db.base import Base, RemarkMixin, TimestampMixin


class SysMenu(Base, TimestampMixin, RemarkMixin):
    """A node of the menu tree.

    Deliberately has no `del_flag`: a removed menu must actually disappear,
    otherwise its `perms` code would linger in the permission set of every role
    that held it.
    """

    __tablename__ = "sys_menu"

    menu_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="菜单ID"
    )
    menu_name: Mapped[str] = mapped_column(String(50), comment="菜单名称")
    parent_id: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), index=True, comment="父菜单ID"
    )
    order_num: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="显示顺序"
    )
    path: Mapped[str | None] = mapped_column(
        String(200), default="", comment="路由地址"
    )
    component: Mapped[str | None] = mapped_column(
        String(255), default=None, comment="组件路径"
    )
    query: Mapped[str | None] = mapped_column(
        String(255), default=None, comment="路由参数"
    )
    route_name: Mapped[str | None] = mapped_column(
        String(50), default="", comment="路由名称"
    )
    is_frame: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), comment="是否外链(0是 1否)"
    )
    is_cache: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="是否缓存(0缓存 1不缓存)"
    )
    menu_type: Mapped[str] = mapped_column(
        String(1),
        default=MenuTypeEnum.MENU,
        server_default=MenuTypeEnum.MENU,
        comment="菜单类型(M目录 C菜单 F按钮)",
    )
    visible: Mapped[str] = mapped_column(
        String(1), default="0", server_default="0", comment="显示状态(0显示 1隐藏)"
    )
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="菜单状态(0正常 1停用)",
    )
    perms: Mapped[str | None] = mapped_column(
        String(100), default=None, index=True, comment="权限标识(如 system:user:add)"
    )
    icon: Mapped[str | None] = mapped_column(String(100), default="#", comment="菜单图标")

    def __repr__(self) -> str:
        return f"<SysMenu {self.menu_id} {self.menu_name!r} type={self.menu_type}>"
