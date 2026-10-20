"""Runtime configuration (`sys_config`).

Key/value rows a running system reads without a redeploy. `config_key` is the business
key the code asks for, so it is unique — enforced in the service layer, not by a
constraint, for the same logical-delete reason as every other business key here.

`is_builtin` marks the rows the application itself depends on. A built-in row may be
edited (that is the point of a config table) but **not deleted** — deleting
`sys.account.captchaEnabled` would not "disable" anything, it would make the lookup
return its fallback and silently change behaviour.
"""

from sqlalchemy import BigInteger, Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, RemarkMixin, SoftDeleteMixin, TimestampMixin


class SysConfig(Base, TimestampMixin, SoftDeleteMixin, RemarkMixin):
    __tablename__ = "sys_config"
    __table_args__ = {"comment": "参数配置表"}

    config_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="参数主键"
    )
    config_name: Mapped[str] = mapped_column(String(100), comment="参数名称")
    config_key: Mapped[str] = mapped_column(String(100), index=True, comment="参数键名(业务键)")
    config_value: Mapped[str] = mapped_column(String(500), default="", comment="参数键值")
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), comment="是否系统内置(内置不可删除)"
    )

    def __repr__(self) -> str:
        return f"<SysConfig {self.config_id} {self.config_key!r}>"
