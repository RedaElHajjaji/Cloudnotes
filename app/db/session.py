"""Async SQLAlchemy engine and session management.

The engine is created once at import time from settings and disposed in the
application lifespan (see ``app.main``). Request-scoped sessions are provided
to FastAPI routes through the :func:`get_db` dependency.
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped database session.

    The session (and its connection) is always closed, even if the request
    handler raises; commits belong to the service layer, not to this
    dependency.
    """
    async with AsyncSessionLocal() as session:
        yield session
