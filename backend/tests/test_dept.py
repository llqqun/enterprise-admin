"""部门 CRUD：树形结构、物化路径维护、以及会破坏层级的操作必须被拒。"""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.models.dept import SysDept
from app.models.user import SysUser

DEPT_URL = "/api/v1/system/dept"


async def _create(client: AsyncClient, headers: dict[str, str], **fields: object) -> dict:
    resp = await client.post(DEPT_URL, headers=headers, json=fields)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


async def _make_root(client: AsyncClient, headers: dict[str, str], name: str) -> dict:
    return await _create(client, headers, parent_id=0, dept_name=name, order_num=1)


# ---------------------------------------------------------------------------
# ancestors（物化路径）
# ---------------------------------------------------------------------------


async def test_root_department_gets_ancestors_zero(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    dept = await _make_root(client, admin_headers, "总部")

    assert dept["parent_id"] == 0
    assert dept["ancestors"] == "0"


async def test_child_appends_its_parent_to_the_path(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    root = await _make_root(client, admin_headers, "总部")

    child = await _create(client, admin_headers, parent_id=root["dept_id"], dept_name="研发部", order_num=1)

    assert child["ancestors"] == f"0,{root['dept_id']}"


async def test_grandchild_path_contains_the_whole_chain(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    root = await _make_root(client, admin_headers, "总部")
    child = await _create(client, admin_headers, parent_id=root["dept_id"], dept_name="研发部", order_num=1)

    leaf = await _create(client, admin_headers, parent_id=child["dept_id"], dept_name="前端组", order_num=1)

    assert leaf["ancestors"] == f"0,{root['dept_id']},{child['dept_id']}"


async def test_moving_a_department_rewrites_its_whole_subtree(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """The single easiest thing to get wrong: only the moved node's path is updated.

    If the descendants keep their stale paths, "本部门及以下" (which walks the same
    tree) and anything reading `ancestors` quietly disagree with the real structure.
    """
    left = await _make_root(client, admin_headers, "研发中心")
    right = await _make_root(client, admin_headers, "市场中心")
    moved = await _create(client, admin_headers, parent_id=left["dept_id"], dept_name="前端组", order_num=1)
    grandchild = await _create(client, admin_headers, parent_id=moved["dept_id"], dept_name="基建组", order_num=1)

    resp = await client.put(
        DEPT_URL,
        headers=admin_headers,
        json={
            "dept_id": moved["dept_id"],
            "parent_id": right["dept_id"],
            "dept_name": "前端组",
            "order_num": 1,
        },
    )
    assert resp.status_code == 200, resp.text

    refreshed_moved = await db_session.scalar(select(SysDept).where(SysDept.dept_id == moved["dept_id"]))
    refreshed_grandchild = await db_session.scalar(
        select(SysDept).where(SysDept.dept_id == grandchild["dept_id"])
    )
    assert refreshed_moved is not None and refreshed_grandchild is not None
    assert refreshed_moved.ancestors == f"0,{right['dept_id']}"
    assert refreshed_grandchild.ancestors == f"0,{right['dept_id']},{moved['dept_id']}"


# ---------------------------------------------------------------------------
# 层级守卫
# ---------------------------------------------------------------------------


async def test_a_department_cannot_be_its_own_parent(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    root = await _make_root(client, admin_headers, "总部")

    resp = await client.put(
        DEPT_URL,
        headers=admin_headers,
        json={"dept_id": root["dept_id"], "parent_id": root["dept_id"], "dept_name": "总部", "order_num": 1},
    )

    assert resp.status_code == 400


async def test_a_department_cannot_be_moved_under_its_own_descendant(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Otherwise the tree becomes a cycle and the recursive CTE never terminates."""
    root = await _make_root(client, admin_headers, "总部")
    child = await _create(client, admin_headers, parent_id=root["dept_id"], dept_name="研发部", order_num=1)

    resp = await client.put(
        DEPT_URL,
        headers=admin_headers,
        json={
            "dept_id": root["dept_id"],
            "parent_id": child["dept_id"],
            "dept_name": "总部",
            "order_num": 1,
        },
    )

    assert resp.status_code == 400
    assert "下级" in resp.json()["msg"]


async def test_delete_is_refused_while_children_exist(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    root = await _make_root(client, admin_headers, "总部")
    await _create(client, admin_headers, parent_id=root["dept_id"], dept_name="研发部", order_num=1)

    resp = await client.delete(f"{DEPT_URL}/{root['dept_id']}", headers=admin_headers)

    assert resp.status_code == 400
    assert "下级" in resp.json()["msg"]


async def test_delete_is_refused_while_users_reference_it(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    dept = await _make_root(client, admin_headers, "研发部")
    db_session.add(
        SysUser(
            user_name="member",
            nick_name="成员",
            password="x",
            dept_id=dept["dept_id"],
            status=StatusEnum.NORMAL,
        )
    )
    await db_session.flush()

    resp = await client.delete(f"{DEPT_URL}/{dept['dept_id']}", headers=admin_headers)

    assert resp.status_code == 400
    assert "用户" in resp.json()["msg"]


async def test_delete_is_soft(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    dept = await _make_root(client, admin_headers, "待撤销部门")

    resp = await client.delete(f"{DEPT_URL}/{dept['dept_id']}", headers=admin_headers)
    assert resp.status_code == 200

    row = await db_session.scalar(
        select(SysDept).where(SysDept.dept_id == dept["dept_id"]).execution_options(include_deleted=True)
    )
    assert row is not None
    assert row.del_flag == DelFlagEnum.DELETED


# ---------------------------------------------------------------------------
# 唯一性与查询
# ---------------------------------------------------------------------------


async def test_duplicate_sibling_name_is_rejected(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    root = await _make_root(client, admin_headers, "总部")
    await _create(client, admin_headers, parent_id=root["dept_id"], dept_name="研发部", order_num=1)

    resp = await client.post(
        DEPT_URL, headers=admin_headers, json={"parent_id": root["dept_id"], "dept_name": "研发部", "order_num": 2}
    )

    assert resp.status_code == 400
    assert "同名" in resp.json()["msg"]


async def test_the_same_name_under_a_different_parent_is_allowed(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Uniqueness is per level, not global — two branches may both have a 研发部."""
    left = await _make_root(client, admin_headers, "华东大区")
    right = await _make_root(client, admin_headers, "华南大区")

    await _create(client, admin_headers, parent_id=left["dept_id"], dept_name="研发部", order_num=1)
    second = await _create(client, admin_headers, parent_id=right["dept_id"], dept_name="研发部", order_num=1)

    assert second["dept_name"] == "研发部"


async def test_renaming_a_department_keeps_its_own_name_unique(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    """Renaming to its own current name must not collide with itself."""
    dept = await _make_root(client, admin_headers, "总部")

    resp = await client.put(
        DEPT_URL,
        headers=admin_headers,
        json={"dept_id": dept["dept_id"], "parent_id": 0, "dept_name": "总部", "order_num": 1},
    )

    assert resp.status_code == 200


async def test_list_returns_a_tree(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    root = await _make_root(client, admin_headers, "总部")
    child = await _create(client, admin_headers, parent_id=root["dept_id"], dept_name="研发部", order_num=1)

    resp = await client.get(DEPT_URL, headers=admin_headers)

    assert resp.status_code == 200
    rows = resp.json()["data"]["rows"]
    top = next(row for row in rows if row["dept_id"] == root["dept_id"])
    assert [node["dept_id"] for node in top["children"]] == [child["dept_id"]]


async def test_treeselect_shape(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    root = await _make_root(client, admin_headers, "总部")

    resp = await client.get(f"{DEPT_URL}/treeselect", headers=admin_headers)

    assert resp.status_code == 200
    nodes = resp.json()["data"]
    node = next(item for item in nodes if item["id"] == root["dept_id"])
    assert node["label"] == "总部"
    assert node["children"] == []


async def test_list_can_filter_by_name(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    await _make_root(client, admin_headers, "总部")
    await _make_root(client, admin_headers, "独立事业部")

    resp = await client.get(DEPT_URL, headers=admin_headers, params={"dept_name": "独立"})

    names = {row["dept_name"] for row in resp.json()["data"]["rows"]}
    assert names == {"独立事业部"}


async def test_get_one_department(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    dept = await _make_root(client, admin_headers, "总部")

    resp = await client.get(f"{DEPT_URL}/{dept['dept_id']}", headers=admin_headers)

    assert resp.status_code == 200
    assert resp.json()["data"]["dept_name"] == "总部"


async def test_get_unknown_department_is_404(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    resp = await client.get(f"{DEPT_URL}/999999", headers=admin_headers)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


async def test_list_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(DEPT_URL)).status_code == 401


async def test_write_requires_the_permission(
    client: AsyncClient, staff_headers: dict[str, str]
) -> None:
    resp = await client.post(
        DEPT_URL, headers=staff_headers, json={"parent_id": 0, "dept_name": "偷偷建的部门", "order_num": 1}
    )

    assert resp.status_code == 403


async def test_delete_requires_the_permission(
    client: AsyncClient, admin_headers: dict[str, str], staff_headers: dict[str, str]
) -> None:
    dept = await _make_root(client, admin_headers, "总部")

    resp = await client.delete(f"{DEPT_URL}/{dept['dept_id']}", headers=staff_headers)

    assert resp.status_code == 403
