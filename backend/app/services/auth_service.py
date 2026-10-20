"""Authentication: captcha, credential verification, lockout, token persistence."""

import uuid
from datetime import timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.config import get_settings
from app.core.constants import WILDCARD_PERM, DelFlagEnum, StatusEnum
from app.core.exceptions import BusinessException, UnauthorizedException
from app.core.security import (
    SESSION_REJECTED_MSG,
    create_token,
    decode_token,
    generate_captcha,
    hash_password,
    verify_password,
)
from app.models.token import SysUserToken
from app.models.user import SysUser
from app.schemas.auth import (
    CaptchaResponse,
    LoginRequest,
    LoginResponse,
    ProfileResponse,
    UserProfile,
)
from app.services.log_service import LOGIN_FAILURE, LOGIN_SUCCESS, record_login_log
from app.utils.request_info import parse_user_agent
from app.utils.timeutil import utcnow

if TYPE_CHECKING:  # avoids a circular import: app.core.deps imports this module
    from app.core.deps import CurrentUser

CAPTCHA_KEY_PREFIX = "captcha:"
CAPTCHA_TTL_SECONDS = 120

LOGIN_FAIL_KEY_PREFIX = "login_fail:"
LOGIN_FAIL_LIMIT = 5
LOGIN_FAIL_WINDOW_SECONDS = 600

CAPTCHA_REJECTED_MSG = "验证码已失效，请刷新后重试"
CREDENTIALS_REJECTED_MSG = "用户名或密码错误"
DISABLED_MSG = "账号已停用，请联系管理员"
LOCKED_MSG = f"密码错误次数过多，账号已锁定 {LOGIN_FAIL_WINDOW_SECONDS // 60} 分钟"


def _lockout_key(user_name: str) -> str:
    """Key the failure counter on the account, not on the spelling of the request.

    MySQL compares `user_name` under the `utf8mb4_0900_ai_ci` collation, which is
    case-insensitive, so `ADMIN` reaches the same row as `admin`. Keying on the raw
    request string handed an attacker a fresh budget for every casing, so the
    documented "5 failures locks the account" held only for one spelling.
    """
    return LOGIN_FAIL_KEY_PREFIX + user_name.strip().casefold()


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """A real bcrypt hash of an unguessable value.

    Verifying against this for a non-existent account costs the same as verifying a
    real one, so response timing does not reveal whether the account exists.
    Computed lazily: hashing at import time would tax every process start.
    """
    return hash_password(uuid.uuid4().hex + uuid.uuid4().hex)


async def build_captcha() -> CaptchaResponse:
    """Mint a captcha and remember its answer under a fresh uuid."""
    if not get_settings().CAPTCHA_ENABLED:
        # Still return a uuid so the client's request shape never changes.
        return CaptchaResponse(uuid=uuid.uuid4().hex, img="", captcha_enabled=False)

    code, image_base64 = generate_captcha()
    captcha_uuid = uuid.uuid4().hex
    await cache.set(CAPTCHA_KEY_PREFIX + captcha_uuid, code, ttl=CAPTCHA_TTL_SECONDS)
    return CaptchaResponse(uuid=captcha_uuid, img=image_base64)


async def _consume_captcha(captcha_uuid: str, code: str) -> None:
    """Verify and burn a captcha.

    The entry is deleted *before* the comparison, so a code can never be replayed —
    not even by the request that gets it wrong.
    """
    if not get_settings().CAPTCHA_ENABLED:
        return

    key = CAPTCHA_KEY_PREFIX + captcha_uuid
    expected = await cache.get(key)
    await cache.delete(key)

    if not expected or str(expected).upper() != code.strip().upper():
        raise BusinessException(CAPTCHA_REJECTED_MSG)


async def _find_user(db: AsyncSession, user_name: str) -> SysUser | None:
    """Look up a live account.

    `del_flag` is already filtered globally, but it is written out here anyway:
    this is the one query where a filter regression would hand out a session rather
    than merely show a deleted row.
    """
    return await db.scalar(
        select(SysUser).where(
            SysUser.user_name == user_name,
            SysUser.del_flag == DelFlagEnum.EXISTS,
        )
    )


async def _issue_tokens(
    db: AsyncSession,
    user: SysUser,
    *,
    ip: str,
    browser: str,
    os_name: str,
) -> LoginResponse:
    """Mint a token pair and persist the session record it belongs to."""
    settings = get_settings()
    access_token, access_jti = create_token(
        user.user_id, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token, refresh_jti = create_token(
        user.user_id, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )

    now = utcnow()
    # 顺手清掉这个账号已经彻底失效的会话行：表从 P0 起只增不减，
    # 而按用户清理是有界的（一次登录最多删掉该账号的旧行），不需要后台任务。
    from app.services.online_service import purge_dead_sessions

    await purge_dead_sessions(db, user.user_id)

    db.add(
        SysUserToken(
            user_id=user.user_id,
            access_jti=access_jti,
            access_expire=now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            refresh_jti=refresh_jti,
            refresh_expire=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            login_ip=ip,
            browser=browser,
            os=os_name,
            login_time=now,
            revoked=False,
        )
    )
    await db.flush()

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def authenticate(
    db: AsyncSession,
    payload: LoginRequest,
    *,
    ip: str,
    user_agent: str,
) -> LoginResponse:
    """Verify a login attempt and issue a token pair.

    Order matters and is deliberate: captcha, then lockout, then credentials. A
    wrong captcha must not count towards the lockout, or anyone who knows a
    username could lock that account without ever guessing its password.
    """
    browser, os_name = parse_user_agent(user_agent)
    audit = {"ipaddr": ip, "browser": browser, "os": os_name}

    await _consume_captcha(payload.uuid, payload.code)

    fail_key = _lockout_key(payload.username)
    if (await cache.get(fail_key) or 0) >= LOGIN_FAIL_LIMIT:
        await record_login_log(
            db,
            user_name=payload.username,
            status=LOGIN_FAILURE,
            msg="账号已锁定",
            **audit,
        )
        raise BusinessException(LOCKED_MSG)

    user = await _find_user(db, payload.username)
    stored_hash = user.password if user is not None else _dummy_password_hash()
    password_ok = verify_password(payload.password, stored_hash)

    if user is None or not password_ok:
        attempts = await cache.incr(fail_key, ttl=LOGIN_FAIL_WINDOW_SECONDS)
        await record_login_log(
            db,
            user_name=payload.username,
            status=LOGIN_FAILURE,
            msg=CREDENTIALS_REJECTED_MSG,
            **audit,
        )
        if attempts >= LOGIN_FAIL_LIMIT:
            raise BusinessException(LOCKED_MSG)
        raise BusinessException(CREDENTIALS_REJECTED_MSG)

    if user.status != StatusEnum.NORMAL:
        await record_login_log(
            db,
            user_name=payload.username,
            status=LOGIN_FAILURE,
            msg=DISABLED_MSG,
            **audit,
        )
        raise BusinessException(DISABLED_MSG)

    result = await _issue_tokens(db, user, ip=ip, browser=browser, os_name=os_name)

    user.login_ip = ip
    user.login_date = utcnow()
    await db.flush()

    await cache.delete(fail_key)
    await record_login_log(
        db,
        user_name=user.user_name,
        status=LOGIN_SUCCESS,
        msg="登录成功",
        **audit,
    )

    return result


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> LoginResponse:
    """Exchange a refresh token for a new pair, rotating the old one out.

    Rotation is what makes replay detectable: the old record is revoked as part of
    the same transaction, so a stolen refresh token is usable at most once — and
    the legitimate client's next refresh then fails, which is a visible signal.
    """
    payload = decode_token(refresh_token, "refresh")
    jti = str(payload["jti"])

    record = await db.scalar(
        select(SysUserToken).where(
            SysUserToken.refresh_jti == jti,
            SysUserToken.revoked.is_(False),
        )
    )
    if record is None or record.refresh_expire < utcnow():
        raise UnauthorizedException(SESSION_REJECTED_MSG)

    user = await db.scalar(select(SysUser).where(SysUser.user_id == record.user_id))
    if user is None or user.status != StatusEnum.NORMAL:
        raise UnauthorizedException(SESSION_REJECTED_MSG)

    record.revoked = True
    await db.flush()

    return await _issue_tokens(
        db, user, ip=record.login_ip, browser=record.browser, os_name=record.os
    )


async def build_profile(db: AsyncSession, current: "CurrentUser") -> ProfileResponse:
    """Assemble the caller's own profile, roles and permission codes.

    The permission list is the same set `require_perm` checks, so the buttons a
    client hides and the calls the server refuses agree by construction.
    """
    user = await db.scalar(select(SysUser).where(SysUser.user_id == current.user_id))
    if user is None or user.status != StatusEnum.NORMAL:
        raise UnauthorizedException(SESSION_REJECTED_MSG)

    roles = [role.role_key for role in user.roles if role.status == StatusEnum.NORMAL]
    permissions = [WILDCARD_PERM] if current.is_admin else sorted(current.perms)

    return ProfileResponse(
        user=UserProfile.model_validate(user),
        roles=roles,
        permissions=permissions,
    )


async def revoke_by_access_jti(db: AsyncSession, access_jti: str) -> None:
    """End the session identified by an access token.

    Revoking the whole row (rather than just the access jti) is what makes logout
    mean "this session is over": the paired refresh token stops working too.
    """
    record = await db.scalar(
        select(SysUserToken).where(SysUserToken.access_jti == access_jti)
    )
    if record is None:
        return
    record.revoked = True
    await db.flush()


# ---------------------------------------------------------------------------
# 改自己的资料 / 改自己的密码
# ---------------------------------------------------------------------------


async def _load_self(db: AsyncSession, current: "CurrentUser") -> SysUser:
    user = await db.scalar(select(SysUser).where(SysUser.user_id == current.user_id))
    if user is None:
        # 令牌有效但账号已经没了：与其它会话失效的情况给同一条消息。
        raise UnauthorizedException("登录状态已失效，请重新登录")
    return user


async def update_own_profile(db: AsyncSession, current: "CurrentUser", payload: Any) -> SysUser:
    """只改 `ProfileUpdate` 里列出的字段。

    这个函数刻意不接受 `user_name` / `status` / `dept_id` / 角色 —— 那些是管理动作，
    走 `PUT /system/user` 并由 `system:user:edit` 保护。在这里放开任何一项都等于给了
    每个登录用户一个提权入口。
    """
    user = await _load_self(db, current)
    # 「没传」与「传了 null」含义不同：前者是不改，后者是清空。
    # 用 `model_fields_set` 区分它们，否则一个只想改昵称的请求会把邮箱顺手清掉。
    provided = payload.model_fields_set
    user.nick_name = payload.nick_name
    if "email" in provided:
        user.email = payload.email
    if "phonenumber" in provided:
        user.phonenumber = payload.phonenumber
    if "sex" in provided and payload.sex is not None:
        # `sys_user.sex` 是 NOT NULL，清空它不是合法请求；传 null 视为不改。
        user.sex = payload.sex
    await db.flush()
    await db.refresh(user)
    return user


async def change_own_password(db: AsyncSession, current: "CurrentUser", payload: Any) -> int:
    """改密码，并让**除当前会话之外**的所有会话失效。返回被撤销的会话数。

    为什么要求原密码：不要求的话，一个被劫持的已登录会话就能把账号锁成自己的。
    为什么撤销其它会话：改密码最常见的动机就是「旧密码可能已经泄露」，那时把别人留在
    登录态里，改密码就白改了。
    """
    user = await _load_self(db, current)

    if not verify_password(payload.old_password, user.password):
        raise BusinessException("原密码不正确")
    if payload.old_password == payload.new_password:
        raise BusinessException("新密码不能与原密码相同")

    user.password = hash_password(payload.new_password)
    user.pwd_update_date = utcnow()

    others = list(
        await db.scalars(
            select(SysUserToken).where(
                SysUserToken.user_id == user.user_id,
                SysUserToken.access_jti != current.access_jti,
                SysUserToken.revoked.is_(False),
            )
        )
    )
    for record in others:
        record.revoked = True

    await db.flush()
    return len(others)
