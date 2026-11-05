"""REST API (JSON). Each module registers its own router here."""

from fastapi import APIRouter

from app.api import analytics, categories, categorization, health, imports, rates, transactions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(transactions.router)
api_router.include_router(analytics.router)
api_router.include_router(imports.router)
api_router.include_router(categories.router)
api_router.include_router(categorization.router)
api_router.include_router(rates.router)
