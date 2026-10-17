"""Declarative base and the column mixins shared by every table."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.constants import DelFlagEnum


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


class TimestampMixin:
    """Audit columns present on every business table (spec section 5.1)."""

    create_by: Mapped[str | None] = mapped_column(String(64), default=None, comment="创建者")
    create_time: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    update_by: Mapped[str | None] = mapped_column(String(64), default=None, comment="更新者")
    update_time: Mapped[datetime | None] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )


class SoftDeleteMixin:
    """Marks a table as logically deletable.

    Rows are never physically removed: `del_flag` flips to '2' and the global
    filter in `app.db.soft_delete` hides them from every ORM query.
    """

    del_flag: Mapped[str] = mapped_column(
        String(1),
        default=DelFlagEnum.EXISTS,
        server_default=DelFlagEnum.EXISTS,
        comment="删除标志(0存在 2删除)",
    )
