"""岗位 CRUD。

这是第一个**真正分页**的接口，所以 P0 评审留下的那条缺口（「分页边界只在模型层被证明过」）
在这里第一次被补到接口层：见文件末尾的分页一节。
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.models.post import SysPost

POST_URL = "/api/v1/system/post"


async def _create(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    resp = await client.post(POST_URL, headers=headers, json=fields)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _make(client: AsyncClient, headers: dict[str, str], code: str, name: str = "岗位", **rest: object) -> dict:
    return await _create(client, headers, post_code=code, post_name=name, post_sort=1, **rest)


# ---------------------------------------------------------------------------
# 基本 CRUD
# ---------------------------------------------------------------------------


async def test_create_then_get(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _make(client, admin_headers, "dev", "研发岗")

    resp = await client.get(f"{POST_URL}/{created['post_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["post_name"] == "研发岗"
    assert resp.json()["data"]["post_code"] == "dev"


async def test_get_unknown_is_404(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    assert (await client.get(f"{POST_URL}/999999", headers=admin_headers)).status_code == 404


async def test_update_changes_fields(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _make(client, admin_headers, "dev", "研发岗")

    resp = await client.put(
        POST_URL,
        headers=admin_headers,
        json={
            "post_id": created["post_id"],
            "post_code": "dev",
            "post_name": "研发工程师",
            "post_sort": 2,
            "status": StatusEnum.DISABLED,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["post_name"] == "研发工程师"
    assert resp.json()["data"]["status"] == StatusEnum.DISABLED


async def test_delete_is_soft(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    created = await _make(client, admin_headers, "dev")

    assert (await client.delete(f"{POST_URL}/{created['post_id']}", headers=admin_headers)).status_code == 200

    row = await db_session.scalar(
        select(SysPost).where(SysPost.post_id == created["post_id"]).execution_options(include_deleted=True)
    )
    assert row is not None and row.del_flag == DelFlagEnum.DELETED


# ---------------------------------------------------------------------------
# 业务键唯一性（P0 承诺但从未实现的那条校验）
# ---------------------------------------------------------------------------


async def test_duplicate_post_code_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "dev", "研发岗")

    resp = await client.post(
        POST_URL, headers=admin_headers, json={"post_code": "dev", "post_name": "另一个岗位", "post_sort": 2}
    )

    assert resp.status_code == 400
    assert "已存在" in resp.json()["msg"]


async def test_a_soft_deleted_code_can_be_reused(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """The whole reason there is no UNIQUE index on `post_code`."""
    first = await _make(client, admin_headers, "dev")
    await client.delete(f"{POST_URL}/{first['post_id']}", headers=admin_headers)

    resp = await client.post(
        POST_URL, headers=admin_headers, json={"post_code": "dev", "post_name": "重建的岗位", "post_sort": 1}
    )

    assert resp.status_code == 200


async def test_update_does_not_collide_with_itself(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _make(client, admin_headers, "dev", "研发岗")

    resp = await client.put(
        POST_URL,
        headers=admin_headers,
        json={
            "post_id": created["post_id"],
            "post_code": "dev",
            "post_name": "研发岗",
            "post_sort": 1,
            "status": StatusEnum.NORMAL,
        },
    )

    assert resp.status_code == 200


async def test_renaming_to_another_existing_code_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "dev")
    other = await _make(client, admin_headers, "ops")

    resp = await client.put(
        POST_URL,
        headers=admin_headers,
        json={
            "post_id": other["post_id"],
            "post_code": "dev",
            "post_name": "运维岗",
            "post_sort": 2,
            "status": StatusEnum.NORMAL,
        },
    )

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 分页（接口层，P0 只证明过模型层）
# ---------------------------------------------------------------------------


async def test_list_uses_the_standard_page_envelope(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "a")
    await _make(client, admin_headers, "b")

    resp = await client.get(POST_URL, headers=admin_headers)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data) == {"rows", "total"}
    assert data["total"] == 2
    assert len(data["rows"]) == 2


async def test_paging_actually_slices(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    for index in range(3):
        await _make(client, admin_headers, f"p{index}")

    resp = await client.get(POST_URL, headers=admin_headers, params={"page_num": 2, "page_size": 2})

    data = resp.json()["data"]
    assert data["total"] == 3
    assert len(data["rows"]) == 1


async def test_oversized_page_size_does_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "a")

    resp = await client.get(POST_URL, headers=admin_headers, params={"page_size": 100000})

    assert resp.status_code == 200
    assert len(resp.json()["data"]["rows"]) == 1


async def test_zero_page_size_does_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "a")

    assert (await client.get(POST_URL, headers=admin_headers, params={"page_size": 0})).status_code == 200


async def test_negative_page_number_does_not_500(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "a")

    assert (await client.get(POST_URL, headers=admin_headers, params={"page_num": -3})).status_code == 200


async def test_non_numeric_page_size_is_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get(POST_URL, headers=admin_headers, params={"page_size": "abc"})

    assert resp.status_code == 422


async def test_non_numeric_page_number_is_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get(POST_URL, headers=admin_headers, params={"page_num": "abc"})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 查询与下拉
# ---------------------------------------------------------------------------


async def test_list_filters_by_name(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _make(client, admin_headers, "dev", "研发岗")
    await _make(client, admin_headers, "ops", "运维岗")

    resp = await client.get(POST_URL, headers=admin_headers, params={"post_name": "研发"})

    assert [row["post_code"] for row in resp.json()["data"]["rows"]] == ["dev"]


async def test_list_filters_by_code(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _make(client, admin_headers, "dev", "研发岗")
    await _make(client, admin_headers, "ops", "运维岗")

    resp = await client.get(POST_URL, headers=admin_headers, params={"post_code": "ops"})

    assert [row["post_name"] for row in resp.json()["data"]["rows"]] == ["运维岗"]


async def test_optionselect_returns_only_enabled_posts(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _make(client, admin_headers, "dev", "研发岗")
    await _make(client, admin_headers, "old", "历史岗位", status=StatusEnum.DISABLED)

    resp = await client.get(f"{POST_URL}/optionselect", headers=admin_headers)

    assert resp.status_code == 200
    codes = [item["post_code"] for item in resp.json()["data"]]
    assert codes == ["dev"]


async def test_optionselect_shape(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _make(client, admin_headers, "dev", "研发岗")

    item = (await client.get(f"{POST_URL}/optionselect", headers=admin_headers)).json()["data"][0]

    assert set(item) == {"post_id", "post_code", "post_name"}


# ---------------------------------------------------------------------------
# 批量删除
# ---------------------------------------------------------------------------


async def test_batch_delete(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    first = await _make(client, admin_headers, "a")
    second = await _make(client, admin_headers, "b")
    keep = await _make(client, admin_headers, "c")

    resp = await client.delete(
        f"{POST_URL}/{first['post_id']},{second['post_id']}", headers=admin_headers
    )

    assert resp.status_code == 200
    remaining = list(await db_session.scalars(select(SysPost.post_id)))
    assert remaining == [keep["post_id"]]


async def test_batch_delete_with_a_non_numeric_id_is_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.delete(f"{POST_URL}/1,abc", headers=admin_headers)

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(POST_URL)).status_code == 401


async def test_write_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(
        POST_URL, headers=staff_headers, json={"post_code": "x", "post_name": "偷偷建的", "post_sort": 1}
    )

    assert resp.status_code == 403


async def test_delete_requires_the_permission(
    client: AsyncClient, admin_headers: dict[str, str], staff_headers: dict[str, str]
) -> None:
    created = await _make(client, admin_headers, "dev")

    resp = await client.delete(f"{POST_URL}/{created['post_id']}", headers=staff_headers)

    assert resp.status_code == 403
