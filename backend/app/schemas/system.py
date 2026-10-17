"""system 模块（部门 / 岗位 / 菜单 / 角色 / 用户）的出入参。

只放这一组模块共用的形状；每个模块的字段留在同一文件里以便对照，因为它们的校验规则
（长度、状态字符、唯一性由 service 层负责）是配套的。
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import StatusEnum
from app.schemas.common import ORMModel


class DeptCreate(BaseModel):
    parent_id: int = Field(default=0, description="父部门ID，0 表示顶级")
    dept_name: str = Field(min_length=1, max_length=50)
    order_num: int = Field(default=0, ge=0)
    leader: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=11)
    email: str | None = Field(default=None, max_length=50)
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    remark: str | None = Field(default=None, max_length=500)


class DeptUpdate(DeptCreate):
    dept_id: int


class DeptOut(ORMModel):
    dept_id: int
    parent_id: int
    ancestors: str
    dept_name: str
    order_num: int
    leader: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    remark: str | None = None


class TreeSelectNode(BaseModel):
    """Element Plus `el-tree-select` 需要的形状。"""

    id: int
    label: str
    children: list["TreeSelectNode"] = Field(default_factory=list)


class PostCreate(BaseModel):
    post_code: str = Field(min_length=1, max_length=64, description="岗位编码（业务键，唯一）")
    post_name: str = Field(min_length=1, max_length=50)
    post_sort: int = Field(default=0, ge=0)
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    remark: str | None = Field(default=None, max_length=500)


class PostUpdate(PostCreate):
    post_id: int


class PostOut(ORMModel):
    post_id: int
    post_code: str
    post_name: str
    post_sort: int
    status: str
    remark: str | None = None
    create_time: datetime | None = None


class PostOption(ORMModel):
    """下拉选项：只给选择必需的三个字段。"""

    post_id: int
    post_code: str
    post_name: str
