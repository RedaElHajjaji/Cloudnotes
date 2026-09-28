"""Database connectivity and readiness checks."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


async def check_database_connection(connection: AsyncConnection) -> dict[str, Any]:
    """Execute a lightweight ``SELECT 1`` probe on the given connection.

    Split from the HTTP layer so both the FastAPI dependency path and tests
    can exercise the same query against real or fake connections.

    Raises any database exception untouched; the API layer maps failures to
    HTTP 503.
    """
    result = await connection.execute(text("SELECT 1"))
    value = result.scalar_one()
    return {"probe": "SELECT 1", "result": value}
