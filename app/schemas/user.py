"""User request/response schemas."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

MIN_PASSWORD_LENGTH = 10
_MAX_PASSWORD_LENGTH = 128

_UPPERCASE = re.compile(r"[A-Z]")
_LOWERCASE = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")


class RegisterRequest(BaseModel):
    """Registration payload: a validated email plus a strong password."""

    email: EmailStr
    password: str = Field(max_length=_MAX_PASSWORD_LENGTH)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        """Enforce minimum length and character-class requirements.

        Rules: at least 10 characters including one uppercase letter, one
        lowercase letter, and one digit. Length is capped by the field
        constraint (128) to bound hashing work.
        """
        if len(value) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
        if not _UPPERCASE.search(value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not _LOWERCASE.search(value):
            raise ValueError("Password must contain at least one lowercase letter")
        if not _DIGIT.search(value):
            raise ValueError("Password must contain at least one digit")
        return value


class LoginRequest(BaseModel):
    """Login payload."""

    email: EmailStr
    password: str = Field(max_length=_MAX_PASSWORD_LENGTH)


class UserRead(BaseModel):
    """Public user representation — never includes ``password_hash``."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """JWT access token issued on successful login."""

    access_token: str
    token_type: str = "bearer"
