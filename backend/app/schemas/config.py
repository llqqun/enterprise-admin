"""参数配置的出入参。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ConfigCreate(BaseModel):
    config_name: str = Field(min_length=1, max_length=100)
    config_key: str = Field(min_length=1, max_length=100, description="业务键，如 sys.account.captchaEnabled")
    config_value: str = Field(default="", max_length=500)
    is_builtin: bool = False
    remark: str | None = Field(default=None, max_length=500)


class ConfigUpdate(ConfigCreate):
    config_id: int


class ConfigOut(ORMModel):
    config_id: int
    config_name: str
    config_key: str
    config_value: str
    is_builtin: bool
    remark: str | None = None
    create_time: datetime | None = None
