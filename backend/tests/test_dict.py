"""字典：类型与数据的增删改查。

两条最容易做错的地方，各有一条测试：
1. 改类型的 `dict_type` 必须级联到数据行 —— 否则整组选项变成孤儿，界面上只表现为「选项全没了」。
2. 类型下还有数据时不允许删除。
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import StatusEnum

TYPE_URL = "/api/v1/system/dict/type"
DATA_URL = "/api/v1/system/dict/data"


async def _type(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    payload = {"dict_name": "性别", "dict_type": "sys_user_sex", **fields}
    resp = await client.post(TYPE_URL, headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _data(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    payload = {
        "dict_type": "sys_user_sex",
        "dict_label": "男",
        "dict_value": "0",
        "dict_sort": 1,
        "tag_type": "success",
        **fields,
    }
    resp = await client.post(DATA_URL, headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# 类型
# ---------------------------------------------------------------------------


async def test_create_type_then_get(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _type(client, admin_headers)

    resp = await client.get(f"{TYPE_URL}/{created['dict_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["dict_type"] == "sys_user_sex"


async def test_type_list_is_paged_and_filterable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _type(client, admin_headers, dict_type="a_type", dict_name="甲")
    await _type(client, admin_headers, dict_type="b_type", dict_name="乙")

    resp = await client.get(TYPE_URL, headers=admin_headers, params={"dict_type": "a_"})

    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["dict_type"] == "a_type"


async def test_duplicate_dict_type_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _type(client, admin_headers)

    resp = await client.post(
        TYPE_URL, headers=admin_headers, json={"dict_name": "另一个", "dict_type": "sys_user_sex"}
    )

    assert resp.status_code == 400
    assert "已存在" in resp.json()["msg"]


async def test_a_soft_deleted_type_can_be_recreated(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _type(client, admin_headers)
    await client.delete(f"{TYPE_URL}/{created['dict_id']}", headers=admin_headers)

    resp = await client.post(
        TYPE_URL, headers=admin_headers, json={"dict_name": "重建", "dict_type": "sys_user_sex"}
    )

    assert resp.status_code == 200


async def test_renaming_the_type_cascades_to_its_data(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """不改数据行的话，那一整组选项就成了孤儿 —— 而界面只会显示「选项全没了」。"""
    created = await _type(client, admin_headers)
    await _data(client, admin_headers)

    resp = await client.put(
        TYPE_URL,
        headers=admin_headers,
        json={
            "dict_id": created["dict_id"],
            "dict_name": "性别",
            "dict_type": "sys_user_gender",
            "status": StatusEnum.NORMAL,
        },
    )
    assert resp.status_code == 200

    moved = await client.get(DATA_URL, headers=admin_headers, params={"dict_type": "sys_user_gender"})
    assert moved.json()["data"]["total"] == 1


async def test_delete_is_refused_while_data_exists(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _type(client, admin_headers)
    await _data(client, admin_headers)

    resp = await client.delete(f"{TYPE_URL}/{created['dict_id']}", headers=admin_headers)

    assert resp.status_code == 400
    assert "还有数据" in resp.json()["msg"]


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------


async def test_data_create_and_lookup(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _type(client, admin_headers)
    await _data(client, admin_headers, dict_label="男", dict_value="0", dict_sort=1)
    await _data(client, admin_headers, dict_label="女", dict_value="1", dict_sort=2)

    resp = await client.get(f"{DATA_URL}/type/sys_user_sex", headers=admin_headers)

    rows = resp.json()["data"]
    assert [row["dict_label"] for row in rows] == ["男", "女"]


async def test_lookup_only_requires_login(client: AsyncClient, admin_headers: dict[str, str], staff_headers: dict[str, str]) -> None:
    """字典是公共词汇表：只会看订单的人也得能把 status=0 显示成「正常」。"""
    await _type(client, admin_headers)
    await _data(client, admin_headers)

    assert (await client.get(f"{DATA_URL}/type/sys_user_sex", headers=staff_headers)).status_code == 200


async def test_lookup_hides_disabled_items(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _type(client, admin_headers)
    await _data(client, admin_headers, dict_label="男", dict_value="0")
    await _data(client, admin_headers, dict_label="未知", dict_value="2", status=StatusEnum.DISABLED)

    rows = (await client.get(f"{DATA_URL}/type/sys_user_sex", headers=admin_headers)).json()["data"]

    assert [row["dict_label"] for row in rows] == ["男"]


async def test_lookup_of_a_disabled_type_is_empty(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """停用一个字典的意图就是「别再用了」，所以整组都不返回。"""
    await _type(client, admin_headers, status=StatusEnum.DISABLED)
    await _data(client, admin_headers)

    rows = (await client.get(f"{DATA_URL}/type/sys_user_sex", headers=admin_headers)).json()["data"]

    assert rows == []


async def test_data_for_an_unknown_type_is_a_400(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.post(
        DATA_URL,
        headers=admin_headers,
        json={"dict_type": "no_such_type", "dict_label": "x", "dict_value": "0"},
    )

    assert resp.status_code == 400
    assert "字典类型不存在" in resp.json()["msg"]


async def test_data_update_and_delete(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _type(client, admin_headers)
    created = await _data(client, admin_headers)

    updated = await client.put(
        DATA_URL,
        headers=admin_headers,
        json={
            "dict_code": created["dict_code"],
            "dict_type": "sys_user_sex",
            "dict_label": "男性",
            "dict_value": "0",
            "dict_sort": 5,
            "tag_type": "info",
            "css_class": "",
            "is_default": True,
            "status": StatusEnum.NORMAL,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["dict_label"] == "男性"

    deleted = await client.delete(f"{DATA_URL}/{created['dict_code']}", headers=admin_headers)
    assert deleted.status_code == 200
    assert (await client.get(f"{DATA_URL}/type/sys_user_sex", headers=admin_headers)).json()["data"] == []


async def test_invalid_tag_type_is_422(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _type(client, admin_headers)

    resp = await client.post(
        DATA_URL,
        headers=admin_headers,
        json={"dict_type": "sys_user_sex", "dict_label": "x", "dict_value": "0", "tag_type": "purple"},
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


async def test_write_requires_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(
        TYPE_URL, headers=staff_headers, json={"dict_name": "偷偷加的", "dict_type": "x_type"}
    )

    assert resp.status_code == 403


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(TYPE_URL)).status_code == 401
