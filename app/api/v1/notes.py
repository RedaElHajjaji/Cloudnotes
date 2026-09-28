"""Note management endpoints (v1).

All routes require authentication. Ownership is enforced in the service and
repository layers; foreign or nonexistent notes are indistinguishable (404),
so ids are not enumerable across users.
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, NoteServiceDependency
from app.schemas import ErrorResponse, NoteCreate, NotePage, NoteRead, NoteUpdate
from app.services.note import NoteNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=NoteRead,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def create_note(
    payload: NoteCreate,
    current_user: CurrentUser,
    note_service: NoteServiceDependency,
) -> NoteRead:
    """Create a note owned by the authenticated user."""
    note = await note_service.create_note(
        owner=current_user,
        title=payload.title,
        content=payload.content,
    )
    return NoteRead.model_validate(note)


@router.get(
    "",
    response_model=NotePage,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
    },
)
async def list_notes(
    current_user: CurrentUser,
    note_service: NoteServiceDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotePage:
    """List the authenticated user's notes, newest first."""
    notes, total = await note_service.list_notes(current_user, limit=limit, offset=offset)
    return NotePage(
        items=[NoteRead.model_validate(note) for note in notes],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{note_id}",
    response_model=NoteRead,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {"model": ErrorResponse, "description": "Note not found (or not owned by you)"},
    },
)
async def get_note(
    note_id: UUID,
    current_user: CurrentUser,
    note_service: NoteServiceDependency,
) -> NoteRead:
    """Retrieve one of the authenticated user's notes."""
    try:
        note = await note_service.get_note(current_user, note_id)
    except NoteNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        ) from None
    return NoteRead.model_validate(note)


@router.put(
    "/{note_id}",
    response_model=NoteRead,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {"model": ErrorResponse, "description": "Note not found (or not owned by you)"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def update_note(
    note_id: UUID,
    payload: NoteUpdate,
    current_user: CurrentUser,
    note_service: NoteServiceDependency,
) -> NoteRead:
    """Update one of the authenticated user's notes (partial update allowed)."""
    try:
        note = await note_service.update_note(
            current_user,
            note_id,
            title=payload.title,
            content=payload.content,
        )
    except NoteNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        ) from None
    return NoteRead.model_validate(note)


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        404: {"model": ErrorResponse, "description": "Note not found (or not owned by you)"},
    },
)
async def delete_note(
    note_id: UUID,
    current_user: CurrentUser,
    note_service: NoteServiceDependency,
) -> None:
    """Delete one of the authenticated user's notes."""
    try:
        await note_service.delete_note(current_user, note_id)
    except NoteNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        ) from None
