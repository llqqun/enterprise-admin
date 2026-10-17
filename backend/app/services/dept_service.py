"""部门：树形 CRUD 与物化路径维护。

`ancestors` 是物化路径（`"0,100,101"`）。它的价值在于「某部门是否在另一部门之下」可以不解树就判断；
它的代价是**任何一次移动或改名都必须重写整棵子树**，否则这个字段会静静地与真实结构脱节 ——
本模块里 `_refresh_subtree_paths` 就是为此存在的，也是这个文件最该被 review 的一段。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.core.exceptions import BusinessException, NotFoundException
from app.models.dept import SysDept
from app.models.user import SysUser
from app.schemas.system import DeptCreate, DeptUpdate
from app.services.data_scope import dept_subtree_ids
from app.utils.tree import build_tree

ROOT_PARENT_ID = 0


# ---------------------------------------------------------------------------
# 内部守卫
# ---------------------------------------------------------------------------


def _ancestors_for(parent: SysDept | None) -> str:
    return "0" if parent is None else f"{parent.ancestors},{parent.dept_id}"


async def _load_parent(db: AsyncSession, parent_id: int) -> SysDept | None:
    if parent_id == ROOT_PARENT_ID:
        return None
    parent = await db.scalar(select(SysDept).where(SysDept.dept_id == parent_id))
    if parent is None:
        raise BusinessException("上级部门不存在")
    return parent


async def _assert_sibling_name_free(
    db: AsyncSession, *, parent_id: int, dept_name: str, exclude_id: int | None = None
) -> None:
    """同一层级下不允许同名。

    唯一性不交给数据库唯一索引，是因为逻辑删除后要允许重建同名部门；
    代价是这条校验必须在 service 层、事务内完成（见 `docs/数据库设计.md` §6）。
    """
    statement = select(SysDept.dept_id).where(
        SysDept.parent_id == parent_id, SysDept.dept_name == dept_name
    )
    if exclude_id is not None:
        statement = statement.where(SysDept.dept_id != exclude_id)
    if await db.scalar(statement.limit(1)) is not None:
        raise BusinessException("同级下已存在同名部门")


async def _assert_not_own_descendant(db: AsyncSession, dept_id: int, new_parent_id: int) -> None:
    """把部门挂到自己的下级下会造出一个环，递归 CTE 将永不终止。"""
    if new_parent_id == ROOT_PARENT_ID:
        return
    if new_parent_id == dept_id:
        raise BusinessException("上级部门不能是自己")
    subtree = await dept_subtree_ids(db, dept_id)
    if new_parent_id in subtree:
        raise BusinessException("上级部门不能是自己的下级")


async def _refresh_subtree_paths(db: AsyncSession, root: SysDept) -> None:
    """`root.ancestors` 变化后，重写它所有下级的路径。

    按路径深度升序处理，这样每一级的父节点在被用到之前已经更新好了。
    """
    subtree = await dept_subtree_ids(db, root.dept_id)
    subtree.discard(root.dept_id)
    if not subtree:
        return

    descendants = list(await db.scalars(select(SysDept).where(SysDept.dept_id.in_(subtree))))
    by_id = {dept.dept_id: dept for dept in descendants}

    for child in sorted(descendants, key=lambda dept: dept.ancestors.count(",")):
        parent = root if child.parent_id == root.dept_id else by_id.get(child.parent_id)
        if parent is None:
            # 数据损坏（父节点不在子树里）：跳过而不是写出更错的路径。
            continue
        child.ancestors = f"{parent.ancestors},{parent.dept_id}"

    await db.flush()


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------


async def get_dept(db: AsyncSession, dept_id: int) -> SysDept:
    dept = await db.scalar(select(SysDept).where(SysDept.dept_id == dept_id))
    if dept is None:
        raise NotFoundException("部门不存在")
    return dept


async def list_depts(
    db: AsyncSession, *, dept_name: str | None = None, status: str | None = None
) -> tuple[list[dict], int]:
    """返回 `(树, 节点总数)`。

    部门列表**不按分页切分**：一棵树被从中间截断就不再是树。响应仍使用统一的分页信封，
    以免前端要为这一个接口写特例。
    """
    statement = select(SysDept).order_by(SysDept.parent_id, SysDept.order_num, SysDept.dept_id)
    if dept_name:
        statement = statement.where(SysDept.dept_name.contains(dept_name))
    if status:
        statement = statement.where(SysDept.status == status)

    depts = list(await db.scalars(statement))
    nodes = [
        {
            "dept_id": dept.dept_id,
            "parent_id": dept.parent_id,
            "ancestors": dept.ancestors,
            "dept_name": dept.dept_name,
            "order_num": dept.order_num,
            "leader": dept.leader,
            "phone": dept.phone,
            "email": dept.email,
            "status": dept.status,
            "remark": dept.remark,
        }
        for dept in depts
    ]
    return build_tree(nodes, id_field="dept_id", parent_field="parent_id"), len(nodes)


async def count_depts(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(SysDept)) or 0)


async def dept_treeselect(db: AsyncSession) -> list[dict]:
    depts = list(await db.scalars(select(SysDept).order_by(SysDept.parent_id, SysDept.order_num)))
    nodes = [
        {"id": dept.dept_id, "parent": dept.parent_id, "label": dept.dept_name} for dept in depts
    ]
    return build_tree(nodes, id_field="id", parent_field="parent")


# ---------------------------------------------------------------------------
# 写入
# ---------------------------------------------------------------------------


async def create_dept(db: AsyncSession, payload: DeptCreate) -> SysDept:
    parent = await _load_parent(db, payload.parent_id)
    await _assert_sibling_name_free(db, parent_id=payload.parent_id, dept_name=payload.dept_name)

    dept = SysDept(
        parent_id=payload.parent_id,
        ancestors=_ancestors_for(parent),
        dept_name=payload.dept_name,
        order_num=payload.order_num,
        leader=payload.leader,
        phone=payload.phone,
        email=payload.email,
        status=payload.status,
        remark=payload.remark,
        del_flag=DelFlagEnum.EXISTS,
    )
    db.add(dept)
    await db.flush()
    return dept


async def update_dept(db: AsyncSession, payload: DeptUpdate) -> SysDept:
    dept = await get_dept(db, payload.dept_id)
    await _assert_not_own_descendant(db, dept.dept_id, payload.parent_id)
    await _assert_sibling_name_free(
        db, parent_id=payload.parent_id, dept_name=payload.dept_name, exclude_id=dept.dept_id
    )

    parent = await _load_parent(db, payload.parent_id)
    moved = dept.parent_id != payload.parent_id

    dept.parent_id = payload.parent_id
    dept.ancestors = _ancestors_for(parent)
    dept.dept_name = payload.dept_name
    dept.order_num = payload.order_num
    dept.leader = payload.leader
    dept.phone = payload.phone
    dept.email = payload.email
    dept.status = payload.status
    dept.remark = payload.remark
    await db.flush()

    if moved:
        await _refresh_subtree_paths(db, dept)

    return dept


async def delete_dept(db: AsyncSession, dept_id: int) -> None:
    dept = await get_dept(db, dept_id)

    if await db.scalar(select(SysDept.dept_id).where(SysDept.parent_id == dept_id).limit(1)):
        raise BusinessException("存在下级部门，不允许删除")
    if await db.scalar(select(SysUser.user_id).where(SysUser.dept_id == dept_id).limit(1)):
        raise BusinessException("部门下存在用户，不允许删除")

    dept.del_flag = DelFlagEnum.DELETED
    await db.flush()


async def status_options(db: AsyncSession) -> list[str]:
    """留给前端筛选下拉的占位：目前只有两种状态。"""
    return [StatusEnum.NORMAL, StatusEnum.DISABLED]
