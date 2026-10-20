"""config

新增 `sys_config`（参数配置）。运行中的系统需要一些不改代码就能改的值；这就是它们的家。

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_config",
        sa.Column("config_id", sa.BigInteger(), autoincrement=True, nullable=False, comment="参数主键"),
        sa.Column("config_name", sa.String(length=100), nullable=False, comment="参数名称"),
        sa.Column("config_key", sa.String(length=100), nullable=False, comment="参数键名(业务键)"),
        sa.Column("config_value", sa.String(length=500), nullable=False, comment="参数键值"),
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="是否系统内置(内置不可删除)",
        ),
        sa.Column("create_by", sa.String(length=64), nullable=True, comment="创建者"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("update_by", sa.String(length=64), nullable=True, comment="更新者"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.Column("del_flag", sa.String(length=1), server_default="0", nullable=False, comment="删除标志(0存在 2删除)"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.PrimaryKeyConstraint("config_id"),
        comment="参数配置表",
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
    )
    op.create_index(op.f("ix_sys_config_config_key"), "sys_config", ["config_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_config_config_key"), table_name="sys_config")
    op.drop_table("sys_config")
