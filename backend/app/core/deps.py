"""Authentication dependencies: who is calling, and what they may do.

`CurrentUser` is the single value every protected endpoint receives. Building it is
the only place that reads the session record, the user's roles and their permission
codes — so there is exactly one implementation of "is this request allowed".
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import ADMIN_ROLE_KEY, WILDCARD_PERM, StatusEnum
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import SESSION_REJECTED_MSG, decode_token
from app.db.session import get_db
from app.models.token import SysUserToken
from app.models.user import SysUser
from app.services.data_scope import DataScope, resolve_data_scope
from app.utils.timeutil import utcnow

MISSING_CREDENTIALS_MSG = "未提供身份凭证"

# auto_error=False so a missing header yields our own envelope instead of
# FastAPI's built-in "Not authenticated" detail.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().API_V1_PREFIX}/auth/login",
    auto_error=False,
)


@dataclass(slots=True)
class CurrentUser:
    """The authenticated caller, as every endpoint sees them."""

    user_id: int
    user_name: str
    dept_id: int | None
    is_admin: bool
    perms: set[str] = field(default_factory=set)
    #: jti of the access token in use. Carried so logout can end exactly this
    #: session rather than every session the account owns.
    access_jti: str = ""
    #: Row-level visibility, resolved once per request from the account's roles.
    data_scope: DataScope = field(default_factory=lambda: DataScope(user_id=0))


def _permission_codes(user: SysUser) -> set[str]:
    """Collect permission codes from every enabled role's enabled menus."""
    codes: set[str] = set()
    for role in user.roles:
        if role.status != StatusEnum.NORMAL:
            continue
        for menu in role.menus:
            if menu.status == StatusEnum.NORMAL and menu.perms:
                codes.add(menu.perms)
    return codes


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Resolve the caller, or raise 401.

    Every rejection raises the same message. Distinguishing "no such session" from
    "expired" from "revoked" would tell an attacker which of their guesses was
    structurally valid.
    """
    request_id = getattr(request.state, "request_id", "-")

    if not token:
        raise UnauthorizedException(MISSING_CREDENTIALS_MSG)

    payload = decode_token(token, "access")
    jti = str(payload["jti"])

    # A JWT is only a claim. The session record is what makes it revocable, so this
    # lookup is the difference between "logged out" and "logged out on paper".
    record = await db.scalar(
        select(SysUserToken).where(
            SysUserToken.access_jti == jti,
            SysUserToken.revoked.is_(False),
        )
    )
    if record is None or record.access_expire < utcnow():
        logger.info("rejected access token [request_id={}] reason=session", request_id)
        raise UnauthorizedException(SESSION_REJECTED_MSG)

    user = await db.scalar(select(SysUser).where(SysUser.user_id == record.user_id))
    if user is None or user.status != StatusEnum.NORMAL:
        # Covers both "the account was disabled/deleted after login" and "the user
        # row vanished". A live token must not outlive the account's right to exist.
        logger.info("rejected access token [request_id={}] reason=account", request_id)
        raise UnauthorizedException(SESSION_REJECTED_MSG)

    role_keys = [role.role_key for role in user.roles if role.status == StatusEnum.NORMAL]
    is_admin = ADMIN_ROLE_KEY in role_keys
    perms = {WILDCARD_PERM} if is_admin else _permission_codes(user)

    current = CurrentUser(
        user_id=user.user_id,
        user_name=user.user_name,
        dept_id=user.dept_id,
        is_admin=is_admin,
        perms=perms,
        access_jti=jti,
        data_scope=resolve_data_scope(
            user.roles, user_id=user.user_id, dept_id=user.dept_id, is_admin=is_admin
        ),
    )
    # 挂到 request.state 上，让「不在接口签名里」的代码（审计装饰器等）也能拿到调用者。
    # 否则每个要记审计的写接口都得为了取个用户名而显式声明一遍 CurrentUser 参数。
    request.state.current_user = current
    return current


def require_perm(perm: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Build a dependency that demands one permission code."""

    async def _dependency(
        current: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if current.is_admin or WILDCARD_PERM in current.perms or perm in current.perms:
            return current
        # Logged at INFO with the code: a 403 is a normal event, but "who tried what"
        # is exactly what an operator needs when a legitimate user reports a wall.
        logger.info("permission denied user={} perm={}", current.user_name, perm)
        raise ForbiddenException()

    return _dependency
