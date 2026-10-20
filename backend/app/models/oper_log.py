"""Operation audit trail (`sys_oper_log`).

Append-only, like `sys_login_log`, but richer: it records *what was done* rather than
*who got in*. The write path is a decorator (`app/services/oper_log_service.py`)
because a middleware cannot see business meaning — it would only know the URL.

`method` / `request_method` naming follows the design spec; `business_type` is an
int so a new kind of operation does not need a schema change.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SysOperLog(Base):
    __tablename__ = "sys_oper_log"
    #: 表注释必须与迁移里的一致，否则 `alembic check` 会报「要删除表注释」的漂移。
    __table_args__ = {"comment": "操作日志表"}

    oper_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="日志主键"
    )
    title: Mapped[str] = mapped_column(String(50), default="", comment="模块标题")
    #: 1 新增 / 2 修改 / 3 删除 / 4 授权 / 5 导出 / 6 导入 / 7 强退 / 9 清空
    business_type: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="业务类型"
    )
    method: Mapped[str] = mapped_column(String(200), default="", comment="方法名称")
    request_method: Mapped[str] = mapped_column(String(10), default="", comment="请求方式")
    oper_name: Mapped[str] = mapped_column(String(50), default="", index=True, comment="操作人员")
    dept_name: Mapped[str] = mapped_column(String(50), default="", comment="部门名称")
    oper_url: Mapped[str] = mapped_column(String(255), default="", comment="请求URL")
    oper_ip: Mapped[str] = mapped_column(String(128), default="", comment="主机地址")
    oper_location: Mapped[str] = mapped_column(String(255), default="", comment="操作地点")
    oper_param: Mapped[str | None] = mapped_column(Text, default=None, comment="请求参数")
    json_result: Mapped[str | None] = mapped_column(Text, default=None, comment="返回参数")
    status: Mapped[str] = mapped_column(
        String(1), default="0", comment="操作状态(0正常 1异常)"
    )
    error_msg: Mapped[str | None] = mapped_column(String(2000), default=None, comment="错误消息")
    cost_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="消耗时间(毫秒)")
    oper_time: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, comment="操作时间"
    )

    def __repr__(self) -> str:
        return f"<SysOperLog {self.oper_id} {self.title!r} status={self.status}>"
