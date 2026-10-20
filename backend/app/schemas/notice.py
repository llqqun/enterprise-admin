"""通知公告的出入参。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import StatusEnum
from app.schemas.common import ORMModel


class NoticeCreate(BaseModel):
    notice_title: str = Field(min_length=1, max_length=50)
    notice_type: str = Field(default="1", pattern="^[12]$", description="1 通知 / 2 公告")
    notice_content: str = Field(default="", max_length=20000)
    #: 0 已发布 / 1 已撤回
    status: str = Field(default=StatusEnum.NORMAL, pattern="^[01]$")
    remark: str | None = Field(default=None, max_length=500)


class NoticeUpdate(NoticeCreate):
    notice_id: int


class NoticeOut(ORMModel):
    notice_id: int
    notice_title: str
    notice_type: str
    notice_content: str
    status: str
    remark: str | None = None
    create_time: datetime | None = None
