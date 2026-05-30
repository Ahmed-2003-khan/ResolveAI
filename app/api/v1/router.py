from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.inbound import router as inbound_router

api_router = APIRouter()

api_router.include_router(health_router)
api_router.include_router(inbound_router)
