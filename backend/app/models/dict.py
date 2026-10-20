"""Dictionaries (`sys_dict_type` + `sys_dict_data`).

Two tables on purpose: a *type* names a list of options (e.g. `sys_user_sex`), a
*data* row is one option. Keeping them apart lets a type exist with no options yet,
and lets options be reordered or disabled without touching the type.

`dict_type` is the business key the frontend asks for (`GET .../data/type/{dictType}`),
so it is unique — but not via a database constraint, for the same logical-delete
reason as every other business key in this schema.
"""

from sqlalchemy import BigInteger, Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import StatusEnum
from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin


class SysDictType(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_dict_type"
    __table_args__ = {"comment": "字典类型表"}

    dict_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="字典主键"
    )
    dict_name: Mapped[str] = mapped_column(String(100), comment="字典名称")
    dict_type: Mapped[str] = mapped_column(String(100), index=True, comment="字典类型(业务键)")
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="状态(0正常 1停用)",
    )

    def __repr__(self) -> str:
        return f"<SysDictType {self.dict_id} {self.dict_type!r}>"


class SysDictData(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_dict_data"
    __table_args__ = {"comment": "字典数据表"}

    dict_code: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="字典编码"
    )
    dict_sort: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="字典排序"
    )
    dict_label: Mapped[str] = mapped_column(String(100), comment="字典标签")
    dict_value: Mapped[str] = mapped_column(String(100), comment="字典键值")
    dict_type: Mapped[str] = mapped_column(String(100), index=True, comment="字典类型")
    #: Element Plus 的 tag 类型（primary/success/warning/danger/info），让状态列有颜色。
    tag_type: Mapped[str] = mapped_column(
        String(20), default="", server_default="", comment="标签样式"
    )
    css_class: Mapped[str] = mapped_column(
        String(100), default="", server_default="", comment="样式类名"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), comment="是否默认选中"
    )
    status: Mapped[str] = mapped_column(
        String(1),
        default=StatusEnum.NORMAL,
        server_default=StatusEnum.NORMAL,
        comment="状态(0正常 1停用)",
    )

    def __repr__(self) -> str:
        return f"<SysDictData {self.dict_code} {self.dict_type}={self.dict_value}>"
