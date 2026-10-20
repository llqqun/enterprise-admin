"""监控模块的出入参。

登录日志是**只读**的审计视图 —— 它与 `sys_oper_log`（操作日志，尚未实现）的区别在于：
前者由认证流程自动写入，后者需要一个装饰器去记录业务动作。
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LoginLogQuery(BaseModel):
    """列表筛选条件。

    `begin_date` / `end_date` 用 `YYYY-MM-DD`：日期是使用者脑子里的粒度，
    让前端去拼出 `2026-10-20T00:00:00+08:00` 这类字符串只会制造时区误会。
    """

    user_name: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, pattern="^[01]$")
    begin_date: str | None = Field(default=None, max_length=10)
    end_date: str | None = Field(default=None, max_length=10)


class LoginLogOut(ORMModel):
    info_id: int
    user_name: str
    ipaddr: str
    login_location: str
    browser: str
    os: str
    status: str
    msg: str
    login_time: datetime


class OperLogOut(ORMModel):
    oper_id: int
    title: str
    business_type: int
    method: str
    request_method: str
    oper_name: str
    dept_name: str
    oper_url: str
    oper_ip: str
    oper_location: str
    oper_param: str | None = None
    json_result: str | None = None
    status: str
    error_msg: str | None = None
    cost_ms: int
    oper_time: datetime
