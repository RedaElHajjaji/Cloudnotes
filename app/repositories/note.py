"""Data access for :class:`~app.models.note.Note`.

Every query is scoped to an owner id at the repository level so object
ownership cannot be bypassed by forgetting a filter elsewhere.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note


class NoteRepository:
    """Encapsulates all persistence operations for notes."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owned(self, note_id: UUID, owner_id: UUID) -> Note | None:
        """Fetch a note by id, only if it belongs to ``owner_id``."""
        statement = select(Note).where(Note.id == note_id, Note.user_id == owner_id)
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        owner_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[Note], int]:
        """Return one page of the owner's notes (newest first) plus total count."""
        total_result = await self._session.execute(
            select(func.count()).select_from(Note).where(Note.user_id == owner_id)
        )
        total = total_result.scalar_one()

        statement = (
            select(Note)
            .where(Note.user_id == owner_id)
            .order_by(Note.created_at.desc(), Note.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all()), total

    async def create(self, owner_id: UUID, title: str, content: str) -> Note:
        """Insert a note owned by ``owner_id``."""
        note = Note(user_id=owner_id, title=title, content=content)
        self._session.add(note)
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def update(
        self,
        note: Note,
        *,
        title: str | None = None,
        content: str | None = None,
    ) -> Note:
        """Apply a partial update and refresh server-side timestamps."""
        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        await self._session.flush()
        await self._session.refresh(note)
        return note

    async def delete(self, note: Note) -> None:
        """Remove a note."""
        await self._session.delete(note)
        await self._session.flush()
