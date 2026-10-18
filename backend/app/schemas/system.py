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


class MenuCreate(BaseModel):
    parent_id: int = Field(default=0, description="父菜单ID，0 表示顶级")
    menu_name: str = Field(min_length=1, max_length=50)
    order_num: int = Field(default=0, ge=0)
    menu_type: str = Field(pattern="^[MCF]$", description="M目录 C菜单 F按钮")
    path: str | None = Field(default=None, max_length=200)
    component: str | None = Field(default=None, max_length=255)
    query: str | None = Field(default=None, max_length=255)
    route_name: str | None = Field(default=None, max_length=50)
    is_frame: int = Field(default=1, ge=0, le=1)
    is_cache: int = Field(default=0, ge=0, le=1)
    visible: str = Field(default="0", pattern="^[01]$")
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    perms: str | None = Field(default=None, max_length=100)
    icon: str | None = Field(default=None, max_length=100)


class MenuUpdate(MenuCreate):
    menu_id: int


class MenuOut(ORMModel):
    menu_id: int
    menu_name: str
    parent_id: int
    order_num: int
    path: str | None = None
    component: str | None = None
    query: str | None = None
    route_name: str | None = None
    is_frame: int = 1
    is_cache: int = 0
    menu_type: str
    visible: str = "0"
    status: str = StatusEnum.NORMAL
    perms: str | None = None
    icon: str | None = None


class RoleMenuTreeSelect(BaseModel):
    menus: list[TreeSelectNode]
    checkedKeys: list[int]


class RoleCreate(BaseModel):
    role_name: str = Field(min_length=1, max_length=30)
    role_key: str = Field(min_length=1, max_length=100, description="权限字符串（业务键，唯一）")
    role_sort: int = Field(default=0, ge=0)
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    remark: str | None = Field(default=None, max_length=500)


class RoleUpdate(RoleCreate):
    role_id: int


class RoleOut(ORMModel):
    role_id: int
    role_name: str
    role_key: str
    role_sort: int
    data_scope: str
    status: str
    remark: str | None = None
    create_time: datetime | None = None


class RoleDataScope(BaseModel):
    role_id: int
    data_scope: str = Field(pattern="^[1-5]$", description="1全部 2自定义 3本部门 4本部门及以下 5仅本人")
    dept_ids: list[int] = Field(default_factory=list)


class RoleStatusChange(BaseModel):
    role_id: int
    status: str = Field(pattern="^[01]$")


class AuthUserRequest(BaseModel):
    role_id: int
    user_id: int


class UserBrief(ORMModel):
    """授权弹窗里的用户行：只给识别与展示必需的字段。"""

    user_id: int
    user_name: str
    nick_name: str
    dept_id: int | None = None
    status: str
