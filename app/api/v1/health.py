"""Health check endpoint."""

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Report service liveness and application version."""
    return {"status": "ok", "version": __version__}
