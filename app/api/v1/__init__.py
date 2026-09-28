"""API version 1.

All v1 routers are assembled into ``api_v1_router`` which the application
mounts under ``/api/v1``. Future business endpoints (notes, tags, auth)
plug in here.
"""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.ready import router as ready_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(ready_router)
