"""Idempotent seed data.

Run with::

    python -m scripts.seed_data

Running it twice must not duplicate anything: every record is looked up by its
business key first, and only created when absent. That makes it safe to re-run
after a partial failure, and safe for a fresh clone to invoke unconditionally.
"""

import asyncio
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DelFlagEnum, StatusEnum
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.models.associations import SysRoleMenu, SysUserPost, SysUserRole
from app.models.config import SysConfig
from app.models.dept import SysDept
from app.models.dict import SysDictData, SysDictType
from app.models.menu import SysMenu
from app.models.notice import SysNotice
from app.models.post import SysPost
from app.models.role import SysRole
from app.models.user import SysUser

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

#: (name, parent name, display order)
DEPARTMENTS: list[tuple[str, str, int]] = [
    ("总公司", "", 1),
    ("研发部", "总公司", 1),
    ("市场部", "总公司", 2),
    ("财务部", "总公司", 3),
]

#: (code, name, display order)
POSTS: list[tuple[str, str, int]] = [
    ("ceo", "董事长", 1),
    ("se", "项目经理", 2),
    ("hr", "人力资源", 3),
]

#: (role key, role name, sort, data scope)
ROLES: list[tuple[str, str, int, str]] = [
    ("admin", "超级管理员", 1, "1"),
    ("dept_manager", "部门主管", 2, "4"),
    ("staff", "普通员工", 3, "5"),
    ("no_menu", "无菜单角色", 4, "5"),
]

#: (user name, nick name, password, role keys, dept name, post codes)
USERS: list[tuple[str, str, str, list[str], str, list[str]]] = [
    ("admin", "超级管理员", "Admin@123456", ["admin"], "总公司", []),
    ("manager", "部门主管", "Manager@123", ["dept_manager"], "研发部", ["se"]),
    ("staff", "普通员工", "Staff@123", ["staff"], "研发部", []),
    ("nobody", "无菜单用户", "Nobody@123", ["no_menu"], "市场部", []),
]

#: (key, name, parent key, order, type, path, component, route name, perms, icon)
#: Icons are Element Plus component names: the frontend renders `menu.meta.icon`
#: through `<component :is="...">`, so an icon here must name a real component.
MENUS: list[tuple[str, str, str, int, str, str | None, str | None, str | None, str | None, str | None]] = [
    ("system", "系统管理", "", 1, "M", "/system", None, "System", None, "Setting"),
    ("system_user", "用户管理", "system", 1, "C", "user", "system/user/index", "SystemUser", "system:user:list", "User"),
    ("system_user_query", "用户查询", "system_user", 1, "F", None, None, None, "system:user:query", None),
    ("system_user_add", "用户新增", "system_user", 2, "F", None, None, None, "system:user:add", None),
    ("system_user_edit", "用户修改", "system_user", 3, "F", None, None, None, "system:user:edit", None),
    ("system_user_remove", "用户删除", "system_user", 4, "F", None, None, None, "system:user:remove", None),
    ("system_role", "角色管理", "system", 2, "C", "role", "system/role/index", "SystemRole", "system:role:list", "UserFilled"),
    ("system_role_query", "角色查询", "system_role", 0, "F", None, None, None, "system:role:query", None),
    ("system_role_add", "角色新增", "system_role", 1, "F", None, None, None, "system:role:add", None),
    ("system_role_edit", "角色修改", "system_role", 2, "F", None, None, None, "system:role:edit", None),
    ("system_role_remove", "角色删除", "system_role", 3, "F", None, None, None, "system:role:remove", None),
    ("system_menu", "菜单管理", "system", 3, "C", "menu", "system/menu/index", "SystemMenu", "system:menu:list", "Grid"),
    ("system_menu_add", "菜单新增", "system_menu", 1, "F", None, None, None, "system:menu:add", None),
    ("system_menu_edit", "菜单修改", "system_menu", 2, "F", None, None, None, "system:menu:edit", None),
    ("system_menu_remove", "菜单删除", "system_menu", 3, "F", None, None, None, "system:menu:remove", None),
    ("system_dept", "部门管理", "system", 4, "C", "dept", "system/dept/index", "SystemDept", "system:dept:list", "Share"),
    ("system_dept_query", "部门查询", "system_dept", 0, "F", None, None, None, "system:dept:query", None),
    ("system_dept_add", "部门新增", "system_dept", 1, "F", None, None, None, "system:dept:add", None),
    ("system_dept_edit", "部门修改", "system_dept", 2, "F", None, None, None, "system:dept:edit", None),
    ("system_dept_remove", "部门删除", "system_dept", 3, "F", None, None, None, "system:dept:remove", None),
    ("system_post", "岗位管理", "system", 5, "C", "post", "system/post/index", "SystemPost", "system:post:list", "Postcard"),
    ("system_post_query", "岗位查询", "system_post", 0, "F", None, None, None, "system:post:query", None),
    ("system_post_add", "岗位新增", "system_post", 1, "F", None, None, None, "system:post:add", None),
    ("system_post_edit", "岗位修改", "system_post", 2, "F", None, None, None, "system:post:edit", None),
    ("system_post_remove", "岗位删除", "system_post", 3, "F", None, None, None, "system:post:remove", None),
    ("system_dict", "字典管理", "system", 6, "C", "dict", "system/dict/index", "SystemDict", "system:dict:list", "Collection"),
    ("system_dict_query", "字典查询", "system_dict", 0, "F", None, None, None, "system:dict:query", None),
    ("system_dict_add", "字典新增", "system_dict", 1, "F", None, None, None, "system:dict:add", None),
    ("system_dict_edit", "字典修改", "system_dict", 2, "F", None, None, None, "system:dict:edit", None),
    ("system_dict_remove", "字典删除", "system_dict", 3, "F", None, None, None, "system:dict:remove", None),
    ("system_config", "参数设置", "system", 7, "C", "config", "system/config/index", "SystemConfig", "system:config:list", "Edit"),
    ("system_config_query", "参数查询", "system_config", 0, "F", None, None, None, "system:config:query", None),
    ("system_config_add", "参数新增", "system_config", 1, "F", None, None, None, "system:config:add", None),
    ("system_config_edit", "参数修改", "system_config", 2, "F", None, None, None, "system:config:edit", None),
    ("system_config_remove", "参数删除", "system_config", 3, "F", None, None, None, "system:config:remove", None),
    ("system_notice", "通知公告", "system", 8, "C", "notice", "system/notice/index", "SystemNotice", "system:notice:list", "Bell"),
    ("system_notice_query", "公告查询", "system_notice", 0, "F", None, None, None, "system:notice:query", None),
    ("system_notice_add", "公告新增", "system_notice", 1, "F", None, None, None, "system:notice:add", None),
    ("system_notice_edit", "公告修改", "system_notice", 2, "F", None, None, None, "system:notice:edit", None),
    ("system_notice_remove", "公告删除", "system_notice", 3, "F", None, None, None, "system:notice:remove", None),
    ("monitor", "监控中心", "", 2, "M", "/monitor", None, "Monitor", None, "Monitor"),
    ("monitor_operlog", "操作日志", "monitor", 1, "C", "operlog", "monitor/operlog/index", "MonitorOperlog", "monitor:operlog:list", "Document"),
    ("monitor_operlog_remove", "操作日志删除", "monitor_operlog", 1, "F", None, None, None, "monitor:operlog:remove", None),
    ("monitor_loginlog", "登录日志", "monitor", 2, "C", "loginlog", "monitor/loginlog/index", "MonitorLoginlog", "monitor:loginlog:list", "List"),
    ("monitor_online", "在线用户", "monitor", 3, "C", "online", "monitor/online/index", "MonitorOnline", "monitor:online:list", "Connection"),
    ("monitor_online_force", "在线用户强退", "monitor_online", 1, "F", None, None, None, "monitor:online:forceLogout", None),
    ("monitor_file", "文件管理", "monitor", 4, "C", "file", "monitor/file/index", "MonitorFile", "monitor:file:list", "Upload"),
    ("monitor_file_upload", "文件上传", "monitor_file", 1, "F", None, None, None, "monitor:file:upload", None),
    ("monitor_file_remove", "文件删除", "monitor_file", 2, "F", None, None, None, "monitor:file:remove", None),
    ("monitor_server", "服务监控", "monitor", 5, "C", "server", "monitor/server/index", "MonitorServer", "monitor:server:list", "Cpu"),
]

#: Menu fields the seeder owns and may refresh on an existing row.
MENU_MUTABLE_FIELDS: tuple[str, ...] = (
    "menu_name",
    "parent_id",
    "order_num",
    "menu_type",
    "path",
    "component",
    "route_name",
    "perms",
    "icon",
    "visible",
    "is_frame",
    "is_cache",
    "status",
)

#: 常用字典：(dict_type, dict_name, [(label, value, sort, tag_type)])。
#: tag_type 直接用 Element Plus 的标签色，让状态列的语义在数据里就定好。
DICTS: list[tuple[str, str, list[tuple[str, str, int, str]]]] = [
    (
        "sys_user_sex",
        "用户性别",
        [("男", "0", 1, "success"), ("女", "1", 2, "warning"), ("未知", "2", 3, "info")],
    ),
    (
        "sys_normal_disable",
        "通用状态",
        [("正常", "0", 1, "success"), ("停用", "1", 2, "danger")],
    ),
    (
        "sys_yes_no",
        "是否",
        [("是", "Y", 1, "success"), ("否", "N", 2, "info")],
    ),
]

#: 内置参数：(config_key, config_name, config_value, is_builtin)。
#: 内置的含义是「不可删除」——删掉一个键不会关闭什么，只会让读取方落到兜底值。
CONFIGS: list[tuple[str, str, str, bool]] = [
    ("sys.account.captchaEnabled", "登录验证码开关", "true", True),
    ("sys.account.registerEnabled", "账号注册开关", "false", True),
    ("sys.index.title", "系统标题", "enterprise-admin", True),
]

#: 初始公告：(title, type, content, status)。type 1 通知 / 2 公告；status 0 已发布 / 1 已撤回。
NOTICES: list[tuple[str, str, str, str]] = [
    (
        "欢迎使用 enterprise-admin",
        "2",
        "这是一个可现场演示的企业级后台管理平台：RBAC 动态路由、按钮级权限与数据权限均已闭环。"
        "用 admin / Manager@123456 之类的账号切换登录，可以看到菜单、按钮与可见数据行数随之变化。",
        "0",
    ),
    (
        "本周六停机维护",
        "1",
        "本周六 22:00 起停机维护约两小时，期间系统不可用。",
        "0",
    ),
]

#: Menu keys each role may see. `"*"` means every menu (the superuser).
ROLE_MENUS: dict[str, list[str] | str] = {
    "admin": "*",
    "dept_manager": [
        "system",
        "system_user",
        "system_user_query",
        "monitor",
        "monitor_online",
    ],
    # Deliberately empty: logging in as `staff` is how the empty-menu path
    # (Review Focus #5) can be demonstrated in the running application.
    "staff": [],
    "no_menu": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_or_create(
    db: AsyncSession, model: Any, *, filters: dict[str, Any], defaults: dict[str, Any] | None = None
) -> tuple[Any, bool]:
    """Return `(instance, created)` for the row matching `filters`."""
    existing = await db.scalar(select(model).filter_by(**filters))
    if existing is not None:
        return existing, False

    instance = model(**{**filters, **(defaults or {})})
    db.add(instance)
    await db.flush()
    return instance, True


async def _upsert_presentation(
    db: AsyncSession,
    model: Any,
    *,
    filters: dict[str, Any],
    defaults: dict[str, Any],
    mutable: tuple[str, ...],
) -> tuple[Any, bool]:
    """Create the row, or refresh its *presentation* fields when it already exists.

    This is what makes the constants above the source of truth: renaming a menu or
    changing an icon and re-running the seeder updates the existing row instead of
    being silently ignored. Only the named fields are touched, so nothing that holds
    user data (a password, a status someone changed deliberately) is overwritten.
    """
    existing = await db.scalar(select(model).filter_by(**filters))
    if existing is None:
        instance = model(**{**filters, **defaults})
        db.add(instance)
        await db.flush()
        return instance, True

    for field in mutable:
        if field in defaults:
            setattr(existing, field, defaults[field])
    await db.flush()
    return existing, False


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------


async def seed_departments(db: AsyncSession) -> dict[str, SysDept]:
    created: dict[str, SysDept] = {}
    for name, parent_name, order_num in DEPARTMENTS:
        parent = created.get(parent_name)
        parent_id = 0 if parent is None else parent.dept_id
        ancestors = "0" if parent is None else f"{parent.ancestors},{parent.dept_id}"

        dept, _ = await _get_or_create(
            db,
            SysDept,
            filters={"dept_name": name},
            defaults={
                "parent_id": parent_id,
                "ancestors": ancestors,
                "order_num": order_num,
                "status": StatusEnum.NORMAL,
                "del_flag": DelFlagEnum.EXISTS,
            },
        )
        created[name] = dept
    return created


async def seed_posts(db: AsyncSession) -> dict[str, SysPost]:
    created: dict[str, SysPost] = {}
    for code, name, sort in POSTS:
        post, _ = await _get_or_create(
            db,
            SysPost,
            filters={"post_code": code},
            defaults={"post_name": name, "post_sort": sort, "status": StatusEnum.NORMAL},
        )
        created[code] = post
    return created


async def seed_roles(db: AsyncSession) -> dict[str, SysRole]:
    created: dict[str, SysRole] = {}
    for key, name, sort, data_scope in ROLES:
        role, _ = await _get_or_create(
            db,
            SysRole,
            filters={"role_key": key},
            defaults={
                "role_name": name,
                "role_sort": sort,
                "data_scope": data_scope,
                "status": StatusEnum.NORMAL,
                "menu_check_strictly": True,
                "dept_check_strictly": True,
            },
        )
        created[key] = role
    return created


async def seed_menus(db: AsyncSession) -> dict[str, SysMenu]:
    """Insert the menu tree in two passes so parents exist before their children."""
    created: dict[str, SysMenu] = {}

    # Pass 1: top-level directories.
    for key, name, parent_key, order_num, menu_type, path, comp, route, perms, icon in MENUS:
        if parent_key:
            continue
        menu, _ = await _upsert_presentation(
            db,
            SysMenu,
            filters={"route_name": route},
            mutable=MENU_MUTABLE_FIELDS,
            defaults={
                "menu_name": name,
                "parent_id": 0,
                "order_num": order_num,
                "menu_type": menu_type,
                "path": path,
                "component": comp,
                "perms": perms,
                "icon": icon,
                "visible": "0",
                "is_frame": 1,
                "is_cache": 0,
                "status": StatusEnum.NORMAL,
            },
        )
        created[key] = menu

    # Pass 2: children. Their parents may themselves be children, so keep iterating
    # until no progress is made — one pass would drop grandchildren silently.
    pending = [row for row in MENUS if row[2]]
    while pending:
        progressed = False
        still_pending = []
        for key, name, parent_key, order_num, menu_type, path, comp, route, perms, icon in pending:
            parent = created.get(parent_key)
            if parent is None:
                still_pending.append((key, name, parent_key, order_num, menu_type, path, comp, route, perms, icon))
                continue

            lookup = {"perms": perms} if perms else {"route_name": route}
            menu, _ = await _upsert_presentation(
                db,
                SysMenu,
                filters=lookup,
                mutable=MENU_MUTABLE_FIELDS,
                defaults={
                    "menu_name": name,
                    "parent_id": parent.menu_id,
                    "order_num": order_num,
                    "menu_type": menu_type,
                    "path": path,
                    "component": comp,
                    "route_name": route,
                    "perms": perms,
                    "icon": icon,
                    "visible": "0",
                    "is_frame": 1,
                    "is_cache": 0,
                    "status": StatusEnum.NORMAL,
                },
            )
            created[key] = menu
            progressed = True

        if not progressed:
            raise RuntimeError(f"menu seed has unresolvable parents: {[row[0] for row in still_pending]}")
        pending = still_pending

    return created


async def link_role_menus(
    db: AsyncSession, roles: dict[str, SysRole], menus: dict[str, SysMenu]
) -> int:
    """Grant each role its menus, skipping links that already exist."""
    existing = {
        (role_id, menu_id)
        for role_id, menu_id in (
            await db.execute(select(SysRoleMenu.role_id, SysRoleMenu.menu_id))
        ).all()
    }

    added = 0
    for role_key, menu_keys in ROLE_MENUS.items():
        role = roles[role_key]
        wanted = list(menus.values()) if menu_keys == "*" else [menus[key] for key in menu_keys]
        for menu in wanted:
            if (role.role_id, menu.menu_id) in existing:
                continue
            db.add(SysRoleMenu(role_id=role.role_id, menu_id=menu.menu_id))
            existing.add((role.role_id, menu.menu_id))
            added += 1
    await db.flush()
    return added


async def seed_users(
    db: AsyncSession,
    depts: dict[str, SysDept],
    roles: dict[str, SysRole],
    posts: dict[str, SysPost],
) -> None:
    for user_name, nick_name, password, role_keys, dept_name, post_codes in USERS:
        user, created = await _get_or_create(
            db,
            SysUser,
            filters={"user_name": user_name},
            defaults={
                "nick_name": nick_name,
                "dept_id": depts[dept_name].dept_id,
                "password": hash_password(password),
                "user_type": "00",
                "status": StatusEnum.NORMAL,
                "del_flag": DelFlagEnum.EXISTS,
            },
        )
        if not created:
            # Never silently reset a password on a re-run; say so instead.
            logger.info("user {} already exists, left untouched", user_name)
            continue

        for role_key in role_keys:
            db.add(SysUserRole(user_id=user.user_id, role_id=roles[role_key].role_id))
        for post_code in post_codes:
            db.add(SysUserPost(user_id=user.user_id, post_id=posts[post_code].post_id))
        await db.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def seed_dicts(db: AsyncSession) -> int:
    """常用字典。

    只刷新展示字段（标签、排序、颜色），不动 `status` —— 有人手工停用了某一项，
    重跑种子不该把它悄悄打开。用 `_upsert_presentation` 正好是这个语义。
    """
    created = 0
    for dict_type, dict_name, items in DICTS:
        await _upsert_presentation(
            db,
            SysDictType,
            filters={"dict_type": dict_type},
            defaults={"dict_name": dict_name},
            mutable=("dict_name",),
        )
        for label, value, sort, tag_type in items:
            _, is_new = await _upsert_presentation(
                db,
                SysDictData,
                filters={"dict_type": dict_type, "dict_value": value},
                defaults={
                    "dict_label": label,
                    "dict_sort": sort,
                    "tag_type": tag_type,
                },
                mutable=("dict_label", "dict_sort", "tag_type"),
            )
            created += int(is_new)
    await db.flush()
    return created


async def seed_configs(db: AsyncSession) -> int:
    """内置参数。

    只刷新名称，**不动 `config_value`** —— 一个值一旦被运维改过，重跑种子不该把它改回去。
    """
    created = 0
    for config_key, config_name, config_value, is_builtin in CONFIGS:
        _, is_new = await _upsert_presentation(
            db,
            SysConfig,
            filters={"config_key": config_key},
            defaults={
                "config_name": config_name,
                "config_value": config_value,
                "is_builtin": is_builtin,
            },
            # 只有名称是可刷新的展示字段；值属于运维的决定。
            mutable=("config_name",),
        )
        created += int(is_new)
    await db.flush()
    return created


async def seed_notices(db: AsyncSession) -> int:
    """初始公告。以标题为业务键，已存在就不再动 —— 有人改过正文或撤回，重跑种子不该覆盖。"""
    created = 0
    for notice_title, notice_type, notice_content, status in NOTICES:
        _, is_new = await _get_or_create(
            db,
            SysNotice,
            filters={"notice_title": notice_title},
            defaults={
                "notice_type": notice_type,
                "notice_content": notice_content,
                "status": status,
                "del_flag": "0",
            },
        )
        created += int(is_new)
    await db.flush()
    return created


async def main() -> None:
    setup_logging()
    async with AsyncSessionLocal() as db:
        depts = await seed_departments(db)
        posts = await seed_posts(db)
        roles = await seed_roles(db)
        menus = await seed_menus(db)
        links = await link_role_menus(db, roles, menus)
        await seed_users(db, depts, roles, posts)
        dict_rows = await seed_dicts(db)
        config_rows = await seed_configs(db)
        notice_rows = await seed_notices(db)
        await db.commit()

    logger.info(
        "seed complete: {} depts, {} posts, {} roles, {} menus, {} role-menu links, "
        "{} dict rows, {} config rows and {} notices created",
        len(depts),
        len(posts),
        len(roles),
        len(menus),
        links,
        dict_rows,
        config_rows,
        notice_rows,
    )
    print()
    print("Seeded accounts (change these before any real deployment):")
    for user_name, _nick, password, role_keys, dept_name, _posts_codes in USERS:
        print(f"  {user_name:<10} {password:<16} roles={','.join(role_keys):<14} dept={dept_name}")


if __name__ == "__main__":
    asyncio.run(main())
