"""Unit tests for security primitives (no database required)."""

import time

import jwt
import pytest
from pydantic import ValidationError

from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.schemas.user import RegisterRequest


def test_hash_and_verify_roundtrip() -> None:
    password_hash = hash_password("Correct-Horse-9")
    assert password_hash != "Correct-Horse-9"
    assert password_hash.startswith("$argon2id$")
    assert verify_password("Correct-Horse-9", password_hash) is True


def test_wrong_password_fails() -> None:
    password_hash = hash_password("Correct-Horse-9")
    assert verify_password("wrong-password-1", password_hash) is False


def test_malformed_hash_is_rejected_safely() -> None:
    assert verify_password("anything-Password1", "not-a-hash") is False


def test_hashes_are_salted_and_unique() -> None:
    assert hash_password("Same-Password-1") != hash_password("Same-Password-1")


def test_password_needs_rehash_detects_outdated_parameters() -> None:
    password_hash = hash_password("Correct-Horse-9")
    assert password_needs_rehash(password_hash) is False


def test_created_token_decodes_to_expected_claims() -> None:
    token = create_access_token("11111111-1111-1111-1111-111111111111")
    claims = decode_access_token(token)
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["iss"] == "cloudnotes"
    assert claims["exp"] > claims["iat"]


def test_garbage_token_is_invalid() -> None:
    with pytest.raises(TokenInvalidError):
        decode_access_token("not.a.jwt")


def test_token_signed_with_wrong_key_is_invalid() -> None:
    other_key = "x" * 48  # >= 32 bytes so PyJWT's key-length warning stays quiet
    token = jwt.encode({"sub": "x", "iat": int(time.time())}, other_key, algorithm="HS256")
    with pytest.raises(TokenInvalidError):
        decode_access_token(token)


def test_expired_token_raises_token_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDNOTES_JWT_ACCESS_TOKEN_EXPIRE_SECONDS", "-10")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        token = create_access_token("user-1")
        with pytest.raises(TokenExpiredError):
            decode_access_token(token)
    finally:
        monkeypatch.undo()  # restore env BEFORE re-caching settings
        get_settings.cache_clear()


# --- Password policy (registration schema) ---


def _register(password: str) -> RegisterRequest:
    return RegisterRequest(email="user@example.com", password=password)


def test_password_policy_accepts_strong_password() -> None:
    assert _register("Sup3r-Secret").password == "Sup3r-Secret"


@pytest.mark.parametrize(
    "password",
    [
        "Sh0rt-1",  # too short
        "alllowercase-1",  # no uppercase
        "ALLUPPERCASE-1",  # no lowercase
        "No-Digits-Here",  # no digit
        "",  # empty
    ],
)
def test_password_policy_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(ValidationError):
        _register(password)


def test_email_must_be_valid() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="Sup3r-Secret")
