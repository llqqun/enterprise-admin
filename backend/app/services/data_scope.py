"""数据权限：把角色的可见范围翻译成查询条件。

设计文档 §6.4 要求多角色取**并集**（权限最大化），所以这里不是「挑一个最宽松的 mode」，
而是保留每个角色的规则、在构造查询时把它们 OR 起来。两者不等价：一个「本部门」角色加一个
「自定义部门」角色，正确结果是两者都能看，而不是只剩自定义的那两个部门。

用法（列表查询的构造处）：

    scope = current.data_scope
    stmt = await apply_data_scope(db, select(SysUser), SysUser, scope)

判定本身是纯函数（`resolve_data_scope`），不需要数据库；只有「本部门及以下」需要查一次子树。
"""

from dataclasses import dataclass
from typing import Any, Sequence

from sqlalchemy import Select, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DataScopeEnum, StatusEnum
from app.models.dept import SysDept
from app.models.role import SysRole

#: 部门列可能为空时用的「不可能匹配」集合，避免把 `IN ()` 发给 MySQL。
_EMPTY = frozenset({-1})


@dataclass(frozen=True)
class ScopeRule:
    """一条角色带来的可见性规则。"""

    mode: int
    dept_id: int | None = None
    custom_dept_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class DataScope:
    """一个请求内解析一次、随后共享的可见范围。

    frozen 是有意的：它会被并发地交给多个查询，可变状态在这里就是竞态。
    """

    user_id: int
    is_admin: bool = False
    rules: tuple[ScopeRule, ...] = ()

    @property
    def unrestricted(self) -> bool:
        """看一眼全部数据。"""
        return self.is_admin or any(rule.mode == int(DataScopeEnum.ALL) for rule in self.rules)

    @property
    def grants_nothing(self) -> bool:
        """没有任何规则 —— 必须**失败关闭**，而不是失败开放。"""
        return not self.unrestricted and not self.rules


def resolve_data_scope(
    roles: Sequence[SysRole],
    *,
    user_id: int,
    dept_id: int | None,
    is_admin: bool,
) -> DataScope:
    """把用户的角色集合解析成可见范围。

    - 管理员直接不受限。
    - 停用或已删除的角色不产生任何规则（与菜单层同样的裁定：被撤销的角色什么都不给）。
    - 同一种 mode 只保留一条；`CUSTOM` 的部门集合取并集。
    - 一个「本部门」类规则遇上没有部门的用户时退化为「仅本人」——否则他一条也看不到，
      而「看不到任何数据」几乎不会是期望的结果。
    """
    if is_admin:
        return DataScope(user_id=user_id, is_admin=True)

    rules: list[ScopeRule] = []
    seen_modes: set[int] = set()
    custom_dept_ids: set[int] = set()

    for role in roles:
        if role.status != StatusEnum.NORMAL:
            continue

        mode = int(role.data_scope)

        if mode == int(DataScopeEnum.CUSTOM):
            custom_dept_ids.update(dept.dept_id for dept in role.depts)
            continue

        if mode in seen_modes:
            continue

        if mode in (int(DataScopeEnum.DEPT), int(DataScopeEnum.DEPT_AND_CHILD)) and dept_id is None:
            if int(DataScopeEnum.SELF) not in seen_modes:
                rules.append(ScopeRule(mode=int(DataScopeEnum.SELF)))
                seen_modes.add(int(DataScopeEnum.SELF))
            continue

        seen_modes.add(mode)
        scoped_to_dept = mode in (int(DataScopeEnum.DEPT), int(DataScopeEnum.DEPT_AND_CHILD))
        rules.append(ScopeRule(mode=mode, dept_id=dept_id if scoped_to_dept else None))

    if custom_dept_ids:
        rules.append(
            ScopeRule(mode=int(DataScopeEnum.CUSTOM), custom_dept_ids=frozenset(custom_dept_ids))
        )

    return DataScope(user_id=user_id, rules=tuple(rules))


async def dept_subtree_ids(db: AsyncSession, root_dept_id: int) -> set[int]:
    """部门子树（含自身）。

    用 MySQL 8 的递归 CTE 在库内一次算完，而不是把整张部门表拉回来在 Python 里遍历 ——
    后者在部门变多时会变成每次列表查询都全表扫描。`SysDept` 的逻辑删除由全局监听器过滤，
    因此已删部门会把它的整条分支一起切断。
    """
    tree = (
        select(SysDept.dept_id)
        .where(SysDept.dept_id == root_dept_id)
        .cte("dept_tree", recursive=True)
    )
    tree = tree.union_all(
        select(SysDept.dept_id).join(tree, SysDept.parent_id == tree.c.dept_id)
    )

    result = await db.execute(select(tree.c.dept_id))
    return set(result.scalars().all())


async def apply_data_scope(
    db: AsyncSession,
    statement: Select[Any],
    entity: Any,
    scope: DataScope,
    *,
    dept_field: str = "dept_id",
    user_field: str = "user_id",
) -> Select[Any]:
    """把可见范围追加到一条查询上。

    `db` 只在「本部门及以下」需要（算子树）。业务代码调用它即可，不应自己写任何
    `if is_admin` 分支 —— 那正是范围判断开始在不同接口之间漂移的起点。
    """
    if scope.unrestricted:
        return statement

    if not scope.rules:
        # 失败关闭：没有规则的账号看到 0 行，而不是看到全部。
        return statement.where(false())

    dept_column = getattr(entity, dept_field)
    user_column = getattr(entity, user_field)

    predicates = []
    for rule in scope.rules:
        if rule.mode == int(DataScopeEnum.SELF):
            predicates.append(user_column == scope.user_id)
        elif rule.mode == int(DataScopeEnum.DEPT):
            predicates.append(dept_column == rule.dept_id)
        elif rule.mode == int(DataScopeEnum.DEPT_AND_CHILD):
            subtree = await dept_subtree_ids(db, rule.dept_id) if rule.dept_id is not None else set()
            predicates.append(dept_column.in_(subtree or _EMPTY))
        elif rule.mode == int(DataScopeEnum.CUSTOM):
            predicates.append(dept_column.in_(rule.custom_dept_ids or _EMPTY))

    if not predicates:
        return statement.where(false())

    return statement.where(or_(*predicates))
