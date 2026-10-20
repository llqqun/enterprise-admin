"""file

新增 `sys_file`（文件记录）。字节存在 `StorageBackend` 后面，表里只存元数据。

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_file",
        sa.Column("file_id", sa.BigInteger(), autoincrement=True, nullable=False, comment="文件ID"),
        sa.Column("stored_name", sa.String(length=128), nullable=False, comment="存储文件名"),
        sa.Column("original_name", sa.String(length=255), nullable=False, comment="原始文件名"),
        sa.Column("storage_path", sa.String(length=255), nullable=False, comment="存储相对路径"),
        sa.Column("extension", sa.String(length=16), nullable=False, comment="扩展名(小写)"),
        sa.Column("content_type", sa.String(length=128), nullable=False, comment="MIME 类型"),
        sa.Column("size_bytes", sa.Integer(), server_default=sa.text("0"), nullable=False, comment="字节数"),
        sa.Column("upload_by", sa.String(length=50), nullable=False, comment="上传人"),
        sa.Column("create_by", sa.String(length=64), nullable=True, comment="创建者"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("update_by", sa.String(length=64), nullable=True, comment="更新者"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.Column("del_flag", sa.String(length=1), server_default="0", nullable=False, comment="删除标志(0存在 2删除)"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.PrimaryKeyConstraint("file_id"),
        comment="文件记录表",
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(op.f("ix_sys_file_upload_by"), "sys_file", ["upload_by"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_file_upload_by"), table_name="sys_file")
    op.drop_table("sys_file")
