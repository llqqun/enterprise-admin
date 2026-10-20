"""字典的出入参。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import StatusEnum
from app.schemas.common import ORMModel


class DictTypeCreate(BaseModel):
    dict_name: str = Field(min_length=1, max_length=100)
    dict_type: str = Field(min_length=1, max_length=100, description="业务键，如 sys_user_sex")
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    remark: str | None = Field(default=None, max_length=500)


class DictTypeUpdate(DictTypeCreate):
    dict_id: int


class DictTypeOut(ORMModel):
    dict_id: int
    dict_name: str
    dict_type: str
    status: str
    remark: str | None = None
    create_time: datetime | None = None


class DictDataCreate(BaseModel):
    dict_type: str = Field(min_length=1, max_length=100)
    dict_label: str = Field(min_length=1, max_length=100)
    dict_value: str = Field(min_length=1, max_length=100)
    dict_sort: int = Field(default=0, ge=0)
    #: Element Plus 支持的标签类型；留空则不套用颜色。
    tag_type: str = Field(default="", pattern="^(|primary|success|info|warning|danger)$")
    css_class: str = Field(default="", max_length=100)
    is_default: bool = False
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    remark: str | None = Field(default=None, max_length=500)


class DictDataUpdate(DictDataCreate):
    dict_code: int


class DictDataOut(ORMModel):
    dict_code: int
    dict_type: str
    dict_label: str
    dict_value: str
    dict_sort: int
    tag_type: str
    css_class: str
    is_default: bool
    status: str
    remark: str | None = None
    create_time: datetime | None = None
