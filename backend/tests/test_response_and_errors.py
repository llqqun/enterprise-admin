"""Unified response envelope, exception hierarchy and global handlers.

The `__test__` routes these tests call are registered by `create_app()` only when
`DEBUG` is on, so they never exist in a production build.
"""

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.response import PageParams, page, success

# ---------------------------------------------------------------------------
# Exception -> HTTP mapping
# ---------------------------------------------------------------------------


async def test_business_exception_maps_to_400_with_code_and_msg(client: AsyncClient) -> None:
    resp = await client.get("/__test__/boom-business")

    assert resp.status_code == 400
    assert resp.json() == {"code": 400, "msg": "库存不足", "data": None}


async def test_forbidden_maps_to_403(client: AsyncClient) -> None:
    resp = await client.get("/__test__/boom-forbidden")

    assert resp.status_code == 403
    assert resp.json() == {"code": 403, "msg": "没有访问权限", "data": None}


async def test_not_found_maps_to_404(client: AsyncClient) -> None:
    resp = await client.get("/__test__/boom-not-found")

    assert resp.status_code == 404
    assert resp.json() == {"code": 404, "msg": "资源不存在", "data": None}


async def test_unhandled_exception_hides_internals(client: AsyncClient) -> None:
    """A 500 must not leak the exception text, the stack, SQL or the DSN."""
    resp = await client.get("/__test__/boom-unhandled")

    assert resp.status_code == 500
    body = resp.json()
    assert body == {"code": 500, "msg": "系统内部错误，请稍后重试", "data": None}

    raw = resp.text
    assert "Traceback" not in raw
    assert "SELECT" not in raw.upper()
    assert "Admin@123456" not in raw
    assert "mysql+asyncmy" not in raw
    assert "kaboom" not in raw


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


async def test_validation_error_returns_422_with_field_details(client: AsyncClient) -> None:
    resp = await client.get("/__test__/validate", params={"q": "abc"})

    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 422
    assert body["msg"] == "参数校验失败"
    assert isinstance(body["data"], list)
    assert body["data"][0]["field"] == "q"


async def test_unknown_route_returns_enveloped_404(client: AsyncClient) -> None:
    resp = await client.get("/no/such/route")

    assert resp.status_code == 404
    assert resp.json()["code"] == 404


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def test_success_helper_shape() -> None:
    assert success({"id": 1}) == {"code": 200, "msg": "操作成功", "data": {"id": 1}}


def test_success_helper_defaults_to_null_data() -> None:
    assert success() == {"code": 200, "msg": "操作成功", "data": None}


def test_page_helper_shape() -> None:
    assert page([{"a": 1}], 5) == {
        "code": 200,
        "msg": "查询成功",
        "data": {"rows": [{"a": 1}], "total": 5},
    }


# ---------------------------------------------------------------------------
# PageParams boundaries (Review Focus #4)
# ---------------------------------------------------------------------------


def test_page_params_defaults() -> None:
    params = PageParams()

    assert params.page_num == 1
    assert params.page_size == 10


def test_page_params_clamps_out_of_range() -> None:
    params = PageParams(page_num=0, page_size=99999)

    assert params.page_num == 1
    assert params.page_size == 100


def test_page_params_negative_size_clamped() -> None:
    assert PageParams(page_size=-1).page_size == 1


def test_page_params_rejects_non_numeric() -> None:
    with pytest.raises(ValidationError):
        PageParams(page_num="abc")


def test_page_params_accepts_boundary_values() -> None:
    params = PageParams(page_num=1, page_size=100)

    assert params.page_num == 1
    assert params.page_size == 100
