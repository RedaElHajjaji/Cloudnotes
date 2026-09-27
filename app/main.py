"""CloudNotes FastAPI application.

Exposes a module-level ``app`` for ``uvicorn app.main:app`` and a
``create_app`` factory used by tests and future deployment targets.
"""

import logging

from fastapi import FastAPI

from app import __version__
from app.api.v1 import api_v1_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
    )

    # Operational health probe at the root, plus the versioned API surface.
    app.include_router(health_router)
    app.include_router(api_v1_router)

    logger.info("CloudNotes API initialized (env=%s)", settings.app_env)
    return app


app = create_app()
