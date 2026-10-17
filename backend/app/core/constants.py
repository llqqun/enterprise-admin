"""Enumerations shared across layers.

Values are the exact strings/ints persisted in MySQL — never renumber them.
"""

from enum import IntEnum, StrEnum


class StatusEnum(StrEnum):
    """Enable/disable flag used by users, roles, menus, depts, dicts."""

    NORMAL = "0"
    DISABLED = "1"


class DelFlagEnum(StrEnum):
    """Logical-delete marker. Mirrors the spec's `0` exists / `2` deleted."""

    EXISTS = "0"
    DELETED = "2"


class MenuTypeEnum(StrEnum):
    """Menu tree node kinds: directory, menu (page), button (permission only)."""

    DIR = "M"
    MENU = "C"
    BUTTON = "F"


class DataScopeEnum(IntEnum):
    """Per-role row-level visibility (see spec section 6.4)."""

    ALL = 1
    CUSTOM = 2
    DEPT = 3
    DEPT_AND_CHILD = 4
    SELF = 5


class BusinessType(IntEnum):
    """Operation-log category."""

    OTHER = 0
    INSERT = 1
    UPDATE = 2
    DELETE = 3
    GRANT = 4
    EXPORT = 5
    IMPORT = 6
    FORCE_LOGOUT = 7
    CLEAN = 9


#: Role key that identifies the superuser.
ADMIN_ROLE_KEY = "admin"

#: Permission code standing for "everything". Granted to the superuser only, so
#: that introducing a new permission can never lock the administrator out.
WILDCARD_PERM = "*:*:*"
