"""Shared FastAPI dependencies (database session, authentication)."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenExpiredError, TokenInvalidError, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth import AuthService
from app.services.note import NoteService

__all__ = ["get_auth_service", "get_current_user", "get_db", "get_note_service"]

# Bearer scheme configured to return 403-style auto-challenges disabled:
# we handle errors ourselves so invalid/missing tokens produce clean 401s.
_bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")


async def get_auth_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[AuthService, None]:
    """Provide an :class:`AuthService` bound to the request's session."""
    yield AuthService(db)


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


async def get_note_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncGenerator[NoteService, None]:
    """Provide a :class:`NoteService` bound to the request's session."""
    yield NoteService(db)


NoteServiceDependency = Annotated[NoteService, Depends(get_note_service)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from a Bearer JWT access token.

    Used by protected endpoints. Raises 401 when the token is missing,
    malformed, expired, or valid but referencing a user that no longer
    exists (e.g. deleted account).
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        claims = decode_access_token(credentials.credentials)
    except (TokenExpiredError, TokenInvalidError):
        raise unauthorized from None

    user = await UserRepository(db).get(claims["sub"])
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
