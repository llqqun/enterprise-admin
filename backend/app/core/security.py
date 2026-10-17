"""Security primitives: password hashing, JWT issuance/validation, captcha.

Kept free of database and HTTP concerns so it can be tested in isolation.
"""

import base64
import io
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt
from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException

TokenType = Literal["access", "refresh"]

ALGORITHM = "HS256"

#: bcrypt hashes at most 72 bytes and (depending on version) either truncates
#: silently or raises. Neither is acceptable, so the limit is enforced here and
#: callers are expected to validate the input before reaching this layer.
BCRYPT_MAX_BYTES = 72
BCRYPT_ROUNDS = 12

#: Characters that look alike are excluded: 0/O, 1/I/l are the classic source of
#: "the captcha is wrong" reports.
CAPTCHA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CAPTCHA_LENGTH = 4

#: One message for every token failure. Telling a caller apart "expired" from
#: "forged" hands them a probing oracle for free.
SESSION_REJECTED_MSG = "登录状态已失效，请重新登录"


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


def hash_password(raw: str) -> str:
    """Hash a plaintext password with bcrypt (per-password salt, cost 12)."""
    encoded = raw.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"password is {len(encoded)} bytes, over bcrypt's {BCRYPT_MAX_BYTES}-byte "
            "limit; validate length before hashing"
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")


def verify_password(raw: str, hashed: str) -> bool:
    """Constant-time-ish comparison that never raises on malformed input."""
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # A corrupt or truncated stored hash is a failed login, not a 500.
        return False


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def create_token(
    user_id: int, token_type: TokenType, expires_delta: timedelta
) -> tuple[str, str]:
    """Return `(token, jti)`.

    The `jti` is returned separately so the caller can persist it in
    `sys_user_token` and later revoke exactly this token.
    """
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    token = jwt.encode(payload, get_settings().SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Decode and validate a token, or raise `UnauthorizedException`.

    Signature, expiry and token type are all checked; every failure raises the
    same message on purpose.
    """
    try:
        payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        # ExpiredSignatureError subclasses InvalidTokenError, so expired,
        # malformed and wrongly-signed tokens all land here. `from None` keeps the
        # original exception out of the traceback.
        raise UnauthorizedException(SESSION_REJECTED_MSG) from None

    if payload.get("type") != expected_type:
        raise UnauthorizedException(SESSION_REJECTED_MSG)

    return payload


# ---------------------------------------------------------------------------
# Captcha
# ---------------------------------------------------------------------------


def _load_captcha_font(size: int) -> Any:
    # Pillow >= 10.1 can scale the built-in font; older versions cannot, and a
    # slightly small captcha is not worth failing a login over.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_captcha(
    width: int = 120, height: int = 40, length: int = CAPTCHA_LENGTH
) -> tuple[str, str]:
    """Return `(code, base64_png)` — base64 carries no `data:` prefix."""
    code = "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(length))

    image = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(image)

    # Interference before the glyphs, so the characters stay legible to a human
    # while a naive OCR pass is not exact.
    for _ in range(6):
        draw.line(
            (
                secrets.randbelow(width),
                secrets.randbelow(height),
                secrets.randbelow(width),
                secrets.randbelow(height),
            ),
            fill=(
                secrets.randbelow(120) + 100,
                secrets.randbelow(120) + 100,
                secrets.randbelow(120) + 100,
            ),
            width=1,
        )
    for _ in range(120):
        draw.point(
            (secrets.randbelow(width), secrets.randbelow(height)),
            fill=(secrets.randbelow(160) + 60, secrets.randbelow(160) + 60, secrets.randbelow(160) + 60),
        )

    font = _load_captcha_font(size=28)
    char_width = width // (length + 1)
    for index, char in enumerate(code):
        draw.text(
            (char_width * (index + 1) - 6, secrets.randbelow(6) + 2),
            char,
            font=font,
            fill=(
                secrets.randbelow(80) + 20,
                secrets.randbelow(80) + 20,
                secrets.randbelow(80) + 20,
            ),
        )

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return code, base64.b64encode(buffer.getvalue()).decode("ascii")
