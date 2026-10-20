"""Notices (`sys_notice`).

`status` here means **published / withdrawn**, not enabled / disabled — a withdrawn
notice disappears from wherever notices are shown, which is what an author expects
when they take one down.
"""

from sqlalchemy import BigInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import StatusEnum
from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin


class SysNotice(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_notice"
    __table_args__ = {"comment": "通知公告表"}

    notice_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="公告ID"
    )
    notice_title: Mapped[str] = mapped_column(String(50), comment="公告标题")
    #: 1 通知 / 2 公告
    notice_type: Mapped[str] = mapped_column(
        String(1), default="1", server_default="1", comment="公告类型(1通知 2公告)"
    )
    notice_content: Mapped[str] = mapped_column(Text, default="", comment="公告内容")
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="状态(0已发布 1已撤回)",
    )

    def __repr__(self) -> str:
        return f"<SysNotice {self.notice_id} {self.notice_title!r}>"
