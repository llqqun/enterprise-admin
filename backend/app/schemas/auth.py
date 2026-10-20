"""Authentication request and response schemas."""

from pydantic import BaseModel, Field, field_validator

from app.core.security import BCRYPT_MAX_BYTES
from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=30, description="账号")
    password: str = Field(min_length=1, description="密码")
    # Not required here on purpose: whether a captcha code must be present depends on
    # runtime configuration (`CAPTCHA_ENABLED`), which is the captcha service's
    # business, not the schema's. The schema validates only shape and length — an
    # empty code against an enabled captcha is a 400 from the service, not a 422 from
    # validation, and those mean different things to a client.
    code: str = Field(default="", max_length=8, description="验证码")
    uuid: str = Field(default="", max_length=64, description="验证码会话标识")

    @field_validator("password")
    @classmethod
    def _reject_over_long_password(cls, value: str) -> str:
        # bcrypt hashes at most 72 bytes. Rejecting here turns what would be a 500
        # from the hashing layer into a clean 422 with a field-level message.
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"密码不能超过 {BCRYPT_MAX_BYTES} 字节")
        return value


class CaptchaResponse(BaseModel):
    uuid: str
    img: str
    captcha_enabled: bool = True


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int = Field(description="访问令牌有效期（秒）")
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserProfile(ORMModel):
    """What a client may know about its own account.

    Note what is absent: `password`. The response cannot leak it because the field
    does not exist here, which is stronger than remembering to strip it.
    """

    user_id: int
    user_name: str
    nick_name: str
    dept_id: int | None = None
    email: str | None = None
    phonenumber: str | None = None
    sex: str | None = None
    avatar: str | None = None
    status: str


class ProfileResponse(BaseModel):
    user: UserProfile
    roles: list[str]
    permissions: list[str]


class ProfileUpdate(BaseModel):
    """用户能改的**自己的**字段。

    刻意不包含：`user_name`（登录身份）、`status`（谁能用这个账号）、`dept_id`（决定数据权限的
    可见范围）、以及任何角色/岗位字段。把它们放进来就是一个越权漏洞 —— 普通用户可以把一个
    被停用的账号自己启用、把自己挪进别的部门（数据权限随之扩大）、或者给自己加角色。
    """

    nick_name: str = Field(min_length=1, max_length=30)
    email: str | None = Field(default=None, max_length=50)
    phonenumber: str | None = Field(default=None, max_length=11)
    sex: str | None = Field(default=None, pattern="^[012]$")


class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=6, max_length=200)

    @field_validator("new_password")
    @classmethod
    def _reject_over_long_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError(f"新密码不能超过 {BCRYPT_MAX_BYTES} 字节")
        return value
