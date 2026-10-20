"""参数配置。

最要紧的一条：**内置参数可改值、不可删除**。删掉一个内置键不会「关闭」什么，
只会让读取方落到兜底值，行为被悄悄改变而页面上看不出异常。
"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum
from app.models.config import SysConfig

CONFIG_URL = "/api/v1/system/config"


async def _config(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    payload = {
        "config_name": "验证码开关",
        "config_key": "sys.account.captchaEnabled",
        "config_value": "true",
        **fields,
    }
    resp = await client.post(CONFIG_URL, headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def test_create_then_get(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await _config(client, admin_headers)

    resp = await client.get(f"{CONFIG_URL}/{created['config_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["config_key"] == "sys.account.captchaEnabled"


async def test_create_time_is_returned(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """`create_time` 是 server_default 列；这条盯着 create 之后有没有 refresh。"""
    created = await _config(client, admin_headers)

    assert created.get("create_time")


async def test_list_is_paged_and_filterable(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _config(client, admin_headers, config_key="a.key", config_name="甲")
    await _config(client, admin_headers, config_key="b.key", config_name="乙")

    resp = await client.get(CONFIG_URL, headers=admin_headers, params={"config_key": "a."})

    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["rows"][0]["config_key"] == "a.key"


async def test_duplicate_key_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _config(client, admin_headers)

    resp = await client.post(
        CONFIG_URL, headers=admin_headers, json={"config_name": "另一个", "config_key": "sys.account.captchaEnabled"}
    )

    assert resp.status_code == 400
    assert "已存在" in resp.json()["msg"]


async def test_junk_key_can_be_recreated(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _config(client, admin_headers)
    await client.delete(f"{CONFIG_URL}/{created['config_id']}", headers=admin_headers)

    resp = await client.post(
        CONFIG_URL, headers=admin_headers, json={"config_name": "重建", "config_key": "sys.account.captchaEnabled"}
    )

    assert resp.status_code == 200


async def test_lookup_by_key_returns_the_value(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    await _config(client, admin_headers, config_value="false")

    resp = await client.get(f"{CONFIG_URL}/configKey/sys.account.captchaEnabled", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"] == "false"


async def test_lookup_of_an_unknown_key_is_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    assert (await client.get(f"{CONFIG_URL}/configKey/no.such.key", headers=admin_headers)).status_code == 404


async def test_lookup_only_requires_login(
    client: AsyncClient, admin_headers: dict[str, str], staff_headers: dict[str, str]
) -> None:
    """读一个开关的值不该需要「参数管理」权限。"""
    await _config(client, admin_headers)

    assert (
        await client.get(f"{CONFIG_URL}/configKey/sys.account.captchaEnabled", headers=staff_headers)
    ).status_code == 200


async def test_update_changes_the_value(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    created = await _config(client, admin_headers)

    resp = await client.put(
        CONFIG_URL,
        headers=admin_headers,
        json={
            "config_id": created["config_id"],
            "config_name": "验证码开关",
            "config_key": "sys.account.captchaEnabled",
            "config_value": "false",
            "is_builtin": False,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["config_value"] == "false"


async def test_builtin_config_can_be_edited_but_not_deleted(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """内置的含义是「不可删除」，不是「不可修改」—— 参数表的意义就是能改。"""
    created = await _config(client, admin_headers, is_builtin=True)

    edited = await client.put(
        CONFIG_URL,
        headers=admin_headers,
        json={
            "config_id": created["config_id"],
            "config_name": "验证码开关",
            "config_key": "sys.account.captchaEnabled",
            "config_value": "false",
            "is_builtin": True,
        },
    )
    assert edited.status_code == 200

    removed = await client.delete(f"{CONFIG_URL}/{created['config_id']}", headers=admin_headers)
    assert removed.status_code == 400
    assert "内置" in removed.json()["msg"]


async def test_builtin_delete_message_names_the_key(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """只说「不允许删除」而不说是哪一个，运维还得自己一个个试。"""
    await _config(client, admin_headers, is_builtin=True, config_key="sys.builtin.one")

    resp = await client.delete(
        f"{CONFIG_URL}/{(await client.get(CONFIG_URL, headers=admin_headers, params={'config_key': 'sys.builtin.one'})).json()['data']['rows'][0]['config_id']}",
        headers=admin_headers,
    )

    assert resp.status_code == 400
    assert "sys.builtin.one" in resp.json()["msg"]


async def test_delete_is_soft(client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession) -> None:
    created = await _config(client, admin_headers)

    assert (await client.delete(f"{CONFIG_URL}/{created['config_id']}", headers=admin_headers)).status_code == 200

    # 软删除：全局过滤器会把它藏起来，所以要显式打开逃生口才看得到这一行还在。
    row = await db_session.scalar(
        select(SysConfig)
        .where(SysConfig.config_id == created["config_id"])
        .execution_options(include_deleted=True)
    )
    assert row is not None
    assert row.del_flag == DelFlagEnum.DELETED


async def test_write_requires_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(
        CONFIG_URL, headers=staff_headers, json={"config_name": "偷偷加的", "config_key": "x.key"}
    )

    assert resp.status_code == 403


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(CONFIG_URL)).status_code == 401
