"""Response schemas for operational endpoints."""

from pydantic import BaseModel


class ReadyResponse(BaseModel):
    """Body of the readiness endpoint (returned for both 200 and 503)."""

    status: str
    database: bool
    version: str
