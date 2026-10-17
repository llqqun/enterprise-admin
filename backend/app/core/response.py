"""Unified response envelope and the pagination contract."""

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, field_validator

SUCCESS_CODE = 200

#: Hard ceiling on page size. Anything larger is clamped rather than rejected so a
#: careless client cannot turn a listing endpoint into a table scan.
MAX_PAGE_SIZE = 100


def success(data: Any = None, msg: str = "操作成功") -> dict[str, Any]:
    """Envelope for a single-object or action response."""
    return {"code": SUCCESS_CODE, "msg": msg, "data": data}


def page(rows: Sequence[Any], total: int) -> dict[str, Any]:
    """Envelope for a listing response."""
    return {
        "code": SUCCESS_CODE,
        "msg": "查询成功",
        "data": {"rows": list(rows), "total": total},
    }


class PageParams(BaseModel):
    """Pagination input, shared by every listing endpoint.

    Out-of-range integers are clamped instead of rejected: a client asking for
    `page_size=99999` gets 100 rows, not an error. Non-numeric input is still a
    validation error (422), because that is a malformed request rather than an
    ambitious one.
    """

    page_num: int = 1
    page_size: int = 10

    @field_validator("page_num")
    @classmethod
    def _clamp_page_num(cls, value: int) -> int:
        return max(1, value)

    @field_validator("page_size")
    @classmethod
    def _clamp_page_size(cls, value: int) -> int:
        return min(MAX_PAGE_SIZE, max(1, value))

    @property
    def offset(self) -> int:
        return (self.page_num - 1) * self.page_size
