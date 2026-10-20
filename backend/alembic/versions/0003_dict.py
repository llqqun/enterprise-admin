"""dict

新增字典两张表：`sys_dict_type`（一组选项的名字）与 `sys_dict_data`（其中的一个选项）。
分成两张表是有意的：一个类型可以在还没有任何选项时就存在，而选项的排序/停用不该牵动类型。

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 两张表共用的建表选项，与 0001 / 0002 保持一致（自动生成不会带上这些）。
TABLE_OPTIONS: dict[str, str] = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


def upgrade() -> None:
    op.create_table(
        "sys_dict_data",
        sa.Column("dict_code", sa.BigInteger(), autoincrement=True, nullable=False, comment="字典编码"),
        sa.Column("dict_sort", sa.Integer(), server_default=sa.text("0"), nullable=False, comment="字典排序"),
        sa.Column("dict_label", sa.String(length=100), nullable=False, comment="字典标签"),
        sa.Column("dict_value", sa.String(length=100), nullable=False, comment="字典键值"),
        sa.Column("dict_type", sa.String(length=100), nullable=False, comment="字典类型"),
        sa.Column("tag_type", sa.String(length=20), server_default="", nullable=False, comment="标签样式"),
        sa.Column("css_class", sa.String(length=100), server_default="", nullable=False, comment="样式类名"),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=False, comment="是否默认选中"),
        sa.Column("status", sa.String(length=1), server_default="0", nullable=False, comment="状态(0正常 1停用)"),
        sa.Column("create_by", sa.String(length=64), nullable=True, comment="创建者"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("update_by", sa.String(length=64), nullable=True, comment="更新者"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.Column("del_flag", sa.String(length=1), server_default="0", nullable=False, comment="删除标志(0存在 2删除)"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.PrimaryKeyConstraint("dict_code"),
        comment="字典数据表",
        **TABLE_OPTIONS,
    )
    op.create_index(op.f("ix_sys_dict_data_dict_type"), "sys_dict_data", ["dict_type"], unique=False)

    op.create_table(
        "sys_dict_type",
        sa.Column("dict_id", sa.BigInteger(), autoincrement=True, nullable=False, comment="字典主键"),
        sa.Column("dict_name", sa.String(length=100), nullable=False, comment="字典名称"),
        sa.Column("dict_type", sa.String(length=100), nullable=False, comment="字典类型(业务键)"),
        sa.Column("status", sa.String(length=1), server_default="0", nullable=False, comment="状态(0正常 1停用)"),
        sa.Column("create_by", sa.String(length=64), nullable=True, comment="创建者"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="创建时间"),
        sa.Column("update_by", sa.String(length=64), nullable=True, comment="更新者"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=True, comment="更新时间"),
        sa.Column("del_flag", sa.String(length=1), server_default="0", nullable=False, comment="删除标志(0存在 2删除)"),
        sa.Column("remark", sa.String(length=500), nullable=True, comment="备注"),
        sa.PrimaryKeyConstraint("dict_id"),
        comment="字典类型表",
        **TABLE_OPTIONS,
    )
    op.create_index(op.f("ix_sys_dict_type_dict_type"), "sys_dict_type", ["dict_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sys_dict_type_dict_type"), table_name="sys_dict_type")
    op.drop_table("sys_dict_type")
    op.drop_index(op.f("ix_sys_dict_data_dict_type"), table_name="sys_dict_data")
    op.drop_table("sys_dict_data")
