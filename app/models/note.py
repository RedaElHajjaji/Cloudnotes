"""Note ORM model."""

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Note(Base, TimestampMixin):
    """A note owned by exactly one user."""

    __tablename__ = "notes"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # User 1:N Note. ``passive_deletes`` lets the database's ON DELETE CASCADE
    # remove notes with their owner, which keeps deletes safe under AsyncSession
    # (no lazy-load of the collection during flush).
    owner: Mapped["User"] = relationship(back_populates="notes")

    def __repr__(self) -> str:
        return f"<Note id={self.id} user_id={self.user_id} title={self.title!r}>"
