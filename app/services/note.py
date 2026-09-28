"""Note business logic."""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note
from app.models.user import User
from app.repositories.note import NoteRepository

logger = logging.getLogger(__name__)


class NoteNotFoundError(Exception):
    """The note does not exist or is not owned by the requesting user."""

    def __init__(self, note_id: UUID) -> None:
        self.note_id = note_id
        super().__init__(f"Note {note_id} not found")


class NoteService:
    """CRUD use cases for notes, scoped to the authenticated owner."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._notes = NoteRepository(session)

    async def create_note(self, owner: User, title: str, content: str) -> Note:
        """Create a note owned by ``owner``."""
        return await self._notes.create(owner_id=owner.id, title=title, content=content)

    async def get_note(self, owner: User, note_id: UUID) -> Note:
        """Return the owner's note or raise :class:`NoteNotFoundError`.

        Ownership is enforced here AND in the repository query itself, so a
        foreign or nonexistent note is indistinguishable (404).
        """
        note = await self._notes.get_owned(note_id, owner.id)
        if note is None:
            raise NoteNotFoundError(note_id)
        return note

    async def list_notes(
        self,
        owner: User,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Note], int]:
        """Return one page of the owner's notes plus the total count."""
        return await self._notes.list_owned(owner.id, limit=limit, offset=offset)

    async def update_note(
        self,
        owner: User,
        note_id: UUID,
        *,
        title: str | None = None,
        content: str | None = None,
    ) -> Note:
        """Partially update the owner's note or raise :class:`NoteNotFoundError`."""
        note = await self._notes.get_owned(note_id, owner.id)
        if note is None:
            raise NoteNotFoundError(note_id)
        return await self._notes.update(note, title=title, content=content)

    async def delete_note(self, owner: User, note_id: UUID) -> None:
        """Delete the owner's note or raise :class:`NoteNotFoundError`."""
        note = await self._notes.get_owned(note_id, owner.id)
        if note is None:
            raise NoteNotFoundError(note_id)
        await self._notes.delete(note)
