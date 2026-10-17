"""Department tree (`sys_dept`)."""

from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import StatusEnum
from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin


class SysDept(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    """A node of the organisation tree.

    The tree is stored as `parent_id` plus a materialised `ancestors` path
    ("0,100,101"). The path makes "is X a descendant of Y" answerable with a LIKE
    on the hot path; the recursive CTE used for data scope stays exact.
    """

    __tablename__ = "sys_dept"

    dept_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="部门ID"
    )
    parent_id: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), index=True, comment="父部门ID"
    )
    ancestors: Mapped[str] = mapped_column(String(50), default="", comment="祖级列表")
    dept_name: Mapped[str] = mapped_column(String(50), comment="部门名称")
    order_num: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="显示顺序"
    )
    leader: Mapped[str | None] = mapped_column(String(20), default=None, comment="负责人")
    phone: Mapped[str | None] = mapped_column(String(11), default=None, comment="联系电话")
    email: Mapped[str | None] = mapped_column(String(50), default=None, comment="邮箱")
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="部门状态(0正常 1停用)",
    )

    def __repr__(self) -> str:
        return f"<SysDept {self.dept_id} {self.dept_name!r}>"
