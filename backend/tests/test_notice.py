"""通知公告。

核心语义：`status` 是**已发布 / 已撤回**。撤回的公告必须从「最新公告」里消失 —— 否则撤回只是
一个装饰性字段。
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.models.notice import SysNotice

NOTICE_URL = "/api/v1/system/notice"


async def _notice(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    payload = {
        "notice_title": "系统维护通知",
        "notice_type": "1",
        "notice_content": "本周六 22:00 起停机维护约两小时。",
        **fields,
    }
    resp = await client.post(NOTICE_URL, headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_create_then_get(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _notice(client, admin_headers)

    resp = await client.get(f"{NOTICE_URL}/{created['notice_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["notice_title"] == "系统维护通知"
    assert resp.json()["data"]["create_time"]


async def test_list_is_paged_and_filterable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _notice(client, admin_headers, notice_title="甲通知", notice_type="1")
    await _notice(client, admin_headers, notice_title="乙公告", notice_type="2")

    by_type = await client.get(NOTICE_URL, headers=admin_headers, params={"notice_type": "2"})
    by_title = await client.get(NOTICE_URL, headers=admin_headers, params={"notice_title": "甲"})

    assert [row["notice_title"] for row in by_type.json()["data"]["rows"]] == ["乙公告"]
    assert [row["notice_title"] for row in by_title.json()["data"]["rows"]] == ["甲通知"]


async def test_latest_only_returns_published(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """撤回的公告出现在首页等于没撤回。"""
    await _notice(client, admin_headers, notice_title="已发布", status=StatusEnum.NORMAL)
    await _notice(client, admin_headers, notice_title="已撤回", status=StatusEnum.DISABLED)

    rows = (await client.get(f"{NOTICE_URL}/latest", headers=admin_headers)).json()["data"]

    assert [row["notice_title"] for row in rows] == ["已发布"]


async def test_latest_is_newest_first_and_limited(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    for index in range(6):
        await _notice(client, admin_headers, notice_title=f"公告{index}")

    rows = (await client.get(f"{NOTICE_URL}/latest", headers=admin_headers)).json()["data"]

    assert len(rows) == 5
    assert rows[0]["notice_title"] == "公告5"


async def test_latest_only_requires_login(
    client: AsyncClient, admin_headers: dict[str, str], staff_headers: dict[str, str]
) -> None:
    """首页要展示公告，而普通员工没有 system:notice:list。"""
    await _notice(client, admin_headers)

    assert (await client.get(f"{NOTICE_URL}/latest", headers=staff_headers)).status_code == 200


async def test_update_changes_content_and_status(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _notice(client, admin_headers)

    resp = await client.put(
        NOTICE_URL,
        headers=admin_headers,
        json={
            "notice_id": created["notice_id"],
            "notice_title": "维护通知（改期）",
            "notice_type": "1",
            "notice_content": "改到下周六。",
            "status": StatusEnum.DISABLED,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["notice_title"] == "维护通知（改期）"
    assert resp.json()["data"]["status"] == StatusEnum.DISABLED


async def test_invalid_type_or_status_is_422(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    bad_type = await client.post(
        NOTICE_URL, headers=admin_headers, json={"notice_title": "x", "notice_type": "9"}
    )
    bad_status = await client.post(
        NOTICE_URL, headers=admin_headers, json={"notice_title": "x", "status": "5"}
    )

    assert bad_type.status_code == 422
    assert bad_status.status_code == 422


async def test_delete_is_soft(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    created = await _notice(client, admin_headers)

    assert (await client.delete(f"{NOTICE_URL}/{created['notice_id']}", headers=admin_headers)).status_code == 200

    from sqlalchemy import select

    row = await db_session.scalar(
        select(SysNotice)
        .where(SysNotice.notice_id == created["notice_id"])
        .execution_options(include_deleted=True)
    )
    assert row is not None
    assert row.del_flag == DelFlagEnum.DELETED


async def test_deleted_notice_disappears_from_latest(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _notice(client, admin_headers)
    await client.delete(f"{NOTICE_URL}/{created['notice_id']}", headers=admin_headers)

    rows = (await client.get(f"{NOTICE_URL}/latest", headers=admin_headers)).json()["data"]

    assert rows == []


async def test_get_unknown_is_404(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    assert (await client.get(f"{NOTICE_URL}/999999", headers=admin_headers)).status_code == 404


async def test_write_requires_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(NOTICE_URL, headers=staff_headers, json={"notice_title": "偷偷发的"})

    assert resp.status_code == 403


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(NOTICE_URL)).status_code == 401
