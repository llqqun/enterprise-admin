"""ORM models.

Every model module must be imported here. Alembic's autogenerate and the global
soft-delete filter both work off `Base.metadata` and the mapper registry, which
only know about classes that have actually been imported.
"""

from app.models.associations import SysRoleDept, SysRoleMenu, SysUserPost, SysUserRole
from app.models.dept import SysDept
from app.models.login_log import SysLoginLog
from app.models.menu import SysMenu
from app.models.oper_log import SysOperLog
from app.models.post import SysPost
from app.models.role import SysRole
from app.models.token import SysUserToken
from app.models.user import SysUser

__all__ = [
    "SysDept",
    "SysLoginLog",
    "SysMenu",
    "SysOperLog",
    "SysPost",
    "SysRole",
    "SysRoleDept",
    "SysRoleMenu",
    "SysUser",
    "SysUserPost",
    "SysUserRole",
    "SysUserToken",
]
