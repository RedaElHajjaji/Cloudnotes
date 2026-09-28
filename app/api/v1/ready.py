"""Readiness endpoint: verifies the application can communicate with PostgreSQL."""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from app import __version__
from app.db.health import check_database_connection
from app.schemas import ReadyResponse

logger = logging.getLogger(__name__)

# Upper bound for the whole probe (connection acquisition + SELECT 1) so a
# slow or firewalled database cannot hang the endpoint.
DB_PROBE_TIMEOUT_SECONDS = 3.0

router = APIRouter(tags=["health"])


def _get_engine(request: Request) -> AsyncEngine:
    """Provide the application's database engine from ``app.state``."""
    return request.app.state.engine


EngineDependency = Annotated[AsyncEngine, Depends(_get_engine)]


@router.get(
    "/ready",
    responses={
        200: {"model": ReadyResponse, "description": "Application is ready"},
        503: {"model": ReadyResponse, "description": "Database is unreachable"},
    },
)
async def readiness_probe(engine: EngineDependency) -> Response:
    """Report readiness: 200 with database details, or 503 if PostgreSQL is unreachable.

    Any failure mode — connection refused, authentication failure, query
    error, or timeout — results in 503 with ``database: false``; the
    exception and traceback are logged for operators.
    """
    try:
        async with asyncio.timeout(DB_PROBE_TIMEOUT_SECONDS):
            async with engine.connect() as connection:
                await check_database_connection(connection)
    except Exception:
        logger.exception("Readiness probe failed: database is unreachable")
        failure = ReadyResponse(status="unavailable", database=False, version=__version__)
        return JSONResponse(status_code=503, content=failure.model_dump())
    success = ReadyResponse(status="ok", database=True, version=__version__)
    return JSONResponse(status_code=200, content=success.model_dump())
