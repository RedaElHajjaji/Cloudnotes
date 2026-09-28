"""Authentication endpoints (v1).

Routing only: validation lives in the schemas, business rules in
:class:`~app.services.auth.AuthService`, HTTP mapping here.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, get_auth_service
from app.schemas import ErrorResponse, LoginRequest, RegisterRequest, TokenResponse, UserRead
from app.services.auth import AuthService, EmailAlreadyRegisteredError, InvalidCredentialsError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserRead,
    responses={
        409: {"model": ErrorResponse, "description": "Email already registered"},
        422: {"model": ErrorResponse, "description": "Validation error (email or password)"},
    },
)
async def register(
    payload: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserRead:
    """Create a new user account.

    The password is stored as an Argon2id hash; plaintext is never persisted
    and never echoed back. Duplicate emails are rejected with 409.
    """
    try:
        user = await auth_service.register_user(email=payload.email, password=payload.password)
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from None
    except IntegrityError:
        logger.exception("Unexpected integrity error during registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        ) from None
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Invalid credentials"},
    },
)
async def login(
    payload: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Exchange email + password for a JWT access token."""
    try:
        user = await auth_service.authenticate(email=payload.email, password=payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    token = auth_service.issue_access_token(user)
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserRead,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def read_current_user(current_user: CurrentUser) -> UserRead:
    """Return the authenticated user (requires a valid Bearer token)."""
    return UserRead.model_validate(current_user)
