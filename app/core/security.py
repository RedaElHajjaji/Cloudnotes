"""Security primitives: password hashing (Argon2id) and JWT handling.

This module is intentionally free of FastAPI routing concerns so the
cryptographic core can be tested and reused in isolation (services, CLI
tooling, future workers).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Argon2id parameters follow the OWASP Password Storage Cheat Sheet
# recommendations for interactive authentication.
_hasher = PasswordHasher()

# JWT errors surfaced as domain exceptions so the API layer can map them to
# HTTP status codes without importing third-party exception types.


class TokenError(Exception):
    """Base class for token validation failures."""


class TokenExpiredError(TokenError):
    """The token is valid but its expiration has passed."""


class TokenInvalidError(TokenError):
    """The token is malformed, wrongly signed, or missing required claims."""


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2id (never store the plaintext)."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a plaintext password against a stored Argon2id hash.

    Returns ``False`` for any mismatch or malformed hash; also transparently
    reports hashes that need rehashing (parameter upgrades) via
    :func:`password_needs_rehash`.
    """
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False
    except (VerificationError, InvalidHashError):
        logger.warning("Malformed password hash encountered during verification")
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Whether the stored hash was produced with outdated Argon2 parameters."""
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(subject: str) -> str:
    """Create a signed JWT access token for the given subject (user id)."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.jwt_access_token_expire_seconds)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token, returning its claims.

    Raises :class:`TokenExpiredError` or :class:`TokenInvalidError` so callers
    never touch ``jwt`` exceptions directly.
    """
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError("Token is invalid") from exc
    if not claims.get("sub"):
        raise TokenInvalidError("Token is missing the subject claim")
    return claims
