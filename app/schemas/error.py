"""API error response schema."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Uniform error body: ``{"detail": "..."}``."""

    detail: str
