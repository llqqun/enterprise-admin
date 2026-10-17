"""Security primitives: password hashing, JWT issuance/validation, captcha."""

import base64
import re
from datetime import timedelta

import pytest

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    CAPTCHA_ALPHABET,
    create_token,
    decode_token,
    generate_captcha,
    hash_password,
    verify_password,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_hash_password_is_not_plaintext() -> None:
    hashed = hash_password("Admin@123456")

    assert hashed != "Admin@123456"
    assert hashed.startswith("$2")  # bcrypt marker


def test_verify_password_accepts_correct_and_rejects_wrong() -> None:
    hashed = hash_password("Admin@123456")

    assert verify_password("Admin@123456", hashed) is True
    assert verify_password("admin@123456", hashed) is False
    assert verify_password("", hashed) is False


def test_same_password_hashes_differently() -> None:
    """A per-password salt is what stops rainbow-table lookups."""
    assert hash_password("Admin@123456") != hash_password("Admin@123456")


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("whatever", "not-a-bcrypt-hash") is False


def test_hash_password_rejects_over_72_bytes() -> None:
    """bcrypt silently truncates past 72 bytes; silent truncation is a bug here."""
    with pytest.raises(ValueError):
        hash_password("a" * 73)


def test_hash_password_accepts_multibyte_password_within_limit() -> None:
    password = "密码" * 12  # 24 chars, 72 UTF-8 bytes exactly

    assert verify_password(password, hash_password(password)) is True


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def test_access_token_roundtrip_carries_user_id_and_jti() -> None:
    token, jti = create_token(7, "access", timedelta(minutes=30))

    payload = decode_token(token, "access")

    assert payload["sub"] == "7"
    assert payload["jti"] == jti
    assert payload["type"] == "access"


def test_each_token_gets_a_distinct_jti() -> None:
    _, first = create_token(7, "access", timedelta(minutes=30))
    _, second = create_token(7, "access", timedelta(minutes=30))

    assert first != second


def test_decode_token_rejects_wrong_type() -> None:
    """An access token must not be usable where a refresh token is required."""
    access_token, _ = create_token(7, "access", timedelta(minutes=30))

    with pytest.raises(UnauthorizedException) as exc:
        decode_token(access_token, "refresh")

    assert exc.value.http_status == 401


def test_decode_token_rejects_expired() -> None:
    token, _ = create_token(7, "access", timedelta(seconds=-1))

    with pytest.raises(UnauthorizedException):
        decode_token(token, "access")


def test_decode_token_rejects_tampered_signature() -> None:
    token, _ = create_token(7, "access", timedelta(minutes=30))
    tampered = token[:-6] + ("aaaaaa" if not token.endswith("aaaaaa") else "bbbbbb")

    with pytest.raises(UnauthorizedException):
        decode_token(tampered, "access")


def test_decode_token_rejects_garbage() -> None:
    with pytest.raises(UnauthorizedException):
        decode_token("not.a.jwt", "access")


def test_token_failures_share_one_message() -> None:
    """Failures must not tell a caller *why* the token was rejected."""
    expired, _ = create_token(7, "access", timedelta(seconds=-1))
    garbage = "not.a.jwt"

    messages = set()
    for token in (expired, garbage):
        with pytest.raises(UnauthorizedException) as exc:
            decode_token(token, "access")
        messages.add(exc.value.msg)

    assert len(messages) == 1


# ---------------------------------------------------------------------------
# Captcha
# ---------------------------------------------------------------------------


def test_captcha_code_length_and_charset() -> None:
    code, _ = generate_captcha()

    assert len(code) == 4
    assert set(code) <= set(CAPTCHA_ALPHABET)


def test_captcha_alphabet_excludes_ambiguous_characters() -> None:
    """0/O, 1/I/l are the classic source of 'the captcha is wrong' support tickets."""
    assert not set("0O1Il") & set(CAPTCHA_ALPHABET)


def test_captcha_image_is_decodable_png() -> None:
    _, image_b64 = generate_captcha()

    raw = base64.b64decode(image_b64)

    assert raw.startswith(PNG_MAGIC)
    assert len(raw) > 200


def test_captcha_is_random() -> None:
    codes = {generate_captcha()[0] for _ in range(30)}

    assert len(codes) > 1


def test_captcha_alphabet_is_alphanumeric() -> None:
    """Guards the alphabet against a careless future edit."""
    assert re.fullmatch(r"[A-Za-z0-9]+", CAPTCHA_ALPHABET)
