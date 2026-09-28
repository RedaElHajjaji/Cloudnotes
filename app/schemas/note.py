"""Note request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MAX_TITLE_LENGTH = 200


class NoteCreate(BaseModel):
    """Payload for creating a note."""

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str = Field(default="", max_length=100_000)


class NoteUpdate(BaseModel):
    """Payload for updating a note.

    At least one field must be provided; omitted fields keep their values.
    """

    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str | None = Field(default=None, max_length=100_000)


class NoteRead(BaseModel):
    """Public note representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    content: str
    created_at: datetime
    updated_at: datetime


class NotePage(BaseModel):
    """One page of the authenticated user's notes."""

    items: list[NoteRead]
    total: int
    limit: int
    offset: int
