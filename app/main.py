"""CloudNotes FastAPI application.

Exposes a module-level ``app`` for ``uvicorn app.main:app`` and a
``create_app`` factory used by tests and future deployment targets.

The lifespan owns the async engine's lifecycle: the shared engine from
``app.db.session`` is attached to ``app.state`` and disposed on shutdown.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1 import api_v1_router
from app.api.v1.health import router as health_router
from app.api.v1.ready import router as ready_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Attach the shared engine at startup and dispose of it at shutdown."""
    app.state.engine = engine
    logger.info("CloudNotes API initialized (env=%s)", get_settings().app_env)
    yield
    await engine.dispose()
    logger.info("Database engine disposed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # Operational probes and the versioned API surface.
    app.include_router(health_router)
    app.include_router(ready_router)
    app.include_router(api_v1_router)

    return app


app = create_app()
