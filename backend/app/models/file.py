"""Uploaded files (`sys_file`).

The row is metadata, not the bytes: the bytes live behind a `StorageBackend` so the
same code can later point at object storage. Two columns exist for security reasons
and are worth understanding before changing anything:

* `stored_name` — a generated name. The client's filename is **never** used as a path,
  because it can contain `..\\`, `/`, NUL bytes or a second extension.
* `original_name` — kept only for display and as the download filename.
"""

from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin


class SysFile(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_file"
    __table_args__ = {"comment": "文件记录表"}

    file_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="文件ID"
    )
    #: 存储用的文件名（服务端生成，不含任何路径分隔符）
    stored_name: Mapped[str] = mapped_column(String(128), comment="存储文件名")
    #: 客户端原始文件名，仅用于展示与下载时的文件名
    original_name: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    #: 相对路径（含按日期分的子目录），不含上传根目录
    storage_path: Mapped[str] = mapped_column(String(255), comment="存储相对路径")
    extension: Mapped[str] = mapped_column(String(16), default="", comment="扩展名(小写)")
    content_type: Mapped[str] = mapped_column(String(128), default="", comment="MIME 类型")
    size_bytes: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), comment="字节数"
    )
    #: 谁传的（登录账号），便于追责
    upload_by: Mapped[str] = mapped_column(String(50), default="", index=True, comment="上传人")

    def __repr__(self) -> str:
        return f"<SysFile {self.file_id} {self.original_name!r}>"
