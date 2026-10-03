"""REST API (JSON). Each module registers its own router here."""

from fastapi import APIRouter

from app.api import health

api_router = APIRouter()
api_router.include_router(health.router)
