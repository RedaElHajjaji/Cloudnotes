"""Authentication business logic.

Separated from routing so the rules live in one testable place (requirement:
authentication code stays out of the API layer).
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)

# Generic failure message: never reveal whether an email exists.
_INVALID_CREDENTIALS = "Incorrect email or password"


class EmailAlreadyRegisteredError(Exception):
    """Raised when registering with an email that already exists."""


class InvalidCredentialsError(Exception):
    """Raised when login credentials do not match any user."""


class AuthService:
    """Registration and login use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def register_user(self, email: str, password: str) -> User:
        """Create a user with an Argon2id hash; reject duplicate emails.

        The duplicate check is best-effort (fast 409 path); the unique index
        is the authoritative guard against races.
        """
        existing = await self._users.get_by_email(email)
        if existing is not None:
            raise EmailAlreadyRegisteredError(email)
        password_hash = hash_password(password)
        try:
            user = await self._users.create(email=email, password_hash=password_hash)
        except IntegrityError:
            raise EmailAlreadyRegisteredError(email) from None
        return user

    async def authenticate(self, email: str, password: str) -> User:
        """Verify credentials and return the user.

        Both the unknown-email and wrong-password paths raise
        :class:`InvalidCredentialsError` with an identical, generic message so
        the response is indistinguishable from the outside.
        """
        user = await self._users.get_by_email(email)
        if user is None:
            # Burn comparable time so user-enumeration via timing is harder.
            hash_password(password)
            raise InvalidCredentialsError(_INVALID_CREDENTIALS)
        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError(_INVALID_CREDENTIALS)
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            logger.info("Rehashing password for user %s (Argon2 parameters upgraded)", user.id)
        return user

    @staticmethod
    def issue_access_token(user: User) -> str:
        """Mint a JWT access token for the given user."""
        return create_access_token(str(user.id))
