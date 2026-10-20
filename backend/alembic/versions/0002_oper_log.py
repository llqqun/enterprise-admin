"""oper log

新增 `sys_oper_log`（操作日志）。与 `sys_login_log` 的区别：那个记录「谁进来了」，
这个记录「谁做了什么」—— 写入者是 `@oper_log` 装饰器，而不是认证流程。

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sys_oper_log",
        sa.Column("oper_id", sa.BigInteger(), autoincrement=True, nullable=False, comment="日志主键"),
        sa.Column("title", sa.String(length=50), nullable=False, comment="模块标题"),
        sa.Column(
            "business_type", sa.Integer(), server_default="0", nullable=False, comment="业务类型"
        ),
        sa.Column("method", sa.String(length=200), nullable=False, comment="方法名称"),
        sa.Column("request_method", sa.String(length=10), nullable=False, comment="请求方式"),
        sa.Column("oper_name", sa.String(length=50), nullable=False, comment="操作人员"),
        sa.Column("dept_name", sa.String(length=50), nullable=False, comment="部门名称"),
        sa.Column("oper_url", sa.String(length=255), nullable=False, comment="请求URL"),
        sa.Column("oper_ip", sa.String(length=128), nullable=False, comment="主机地址"),
        sa.Column("oper_location", sa.String(length=255), nullable=False, comment="操作地点"),
        sa.Column("oper_param", sa.Text(), nullable=True, comment="请求参数"),
        sa.Column("json_result", sa.Text(), nullable=True, comment="返回参数"),
        sa.Column("status", sa.String(length=1), nullable=False, comment="操作状态(0正常 1异常)"),
        sa.Column("error_msg", sa.String(length=2000), nullable=True, comment="错误消息"),
        sa.Column(
            "cost_ms", sa.Integer(), server_default="0", nullable=False, comment="消耗时间(毫秒)"
        ),
        sa.Column(
            "oper_time",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
            comment="操作时间",
        ),
        sa.PrimaryKeyConstraint("oper_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        comment="操作日志表",
    )
    op.create_index(op.f("ix_sys_oper_log_oper_name"), "sys_oper_log", ["oper_name"], unique=False)
    op.create_index(op.f("ix_sys_oper_log_oper_time"), "sys_oper_log", ["oper_time"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_oper_log_oper_time"), table_name="sys_oper_log")
    op.drop_index(op.f("ix_sys_oper_log_oper_name"), table_name="sys_oper_log")
    op.drop_table("sys_oper_log")
