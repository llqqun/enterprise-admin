"""文件记录的出入参。

注意这里**没有** `storage_path`：存储路径是服务端实现细节，暴露出去只会诱使调用方去拼路径。
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class FileOut(ORMModel):
    file_id: int
    original_name: str
    extension: str
    content_type: str
    size_bytes: int
    upload_by: str
    create_time: datetime | None = None


class FileQuery(BaseModel):
    original_name: str | None = Field(default=None, max_length=255)
