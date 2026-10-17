"""Job posts (`sys_post`)."""

from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import StatusEnum
from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin


class SysPost(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_post"

    post_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="岗位ID"
    )
    post_code: Mapped[str] = mapped_column(
        String(64), index=True, comment="岗位编码(业务键)"
    )
    post_name: Mapped[str] = mapped_column(String(50), comment="岗位名称")
    post_sort: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="显示顺序"
    )
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="状态(0正常 1停用)",
    )

    def __repr__(self) -> str:
        return f"<SysPost {self.post_id} {self.post_code!r}>"
