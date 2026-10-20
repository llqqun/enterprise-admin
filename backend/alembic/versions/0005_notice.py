"""notice

新增 `sys_notice`（通知公告）。`status` 的语义是**已发布 / 已撤回**，不是启用 / 停用 ——
撤回一条公告的预期就是它从展示处消失。

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_notice",
        sa.Column("notice_id", sa.BigInteger(), autoincrement=True, nullable=False, comment="公告ID"),
        sa.Column("notice_title", sa.String(length=50), nullable=False, comment="公告标题"),
        sa.Column("notice_type", sa.String(length=1), server_default="1", nullable=False, comment="公告类型(1通知 2公告)"),
        sa.Column("notice_content", sa.Text(), nullable=False, comment="公告内容"),
        sa.Column("status", sa.String(length=1), server_default="0", nullable=False, comment="状态(0已发布 1已撤回)"),
        sa.Column("create_by", sa.String(length=64), nullable=True, comment="创建者"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("update_by", sa.String(length=64), nullable=True, comment="更新者"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.Column("del_flag", sa.String(length=1), server_default="0", nullable=False, comment="删除标志(0存在 2删除)"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.PrimaryKeyConstraint("notice_id"),
        comment="通知公告表",
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )


def downgrade() -> None:
    op.drop_table("sys_notice")
