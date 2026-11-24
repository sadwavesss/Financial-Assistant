"""Server-rendered HTML pages."""

from fastapi import APIRouter

from app.web import (
    analytics,
    categories,
    categorization,
    forecast,
    imports,
    pages,
    recommendations,
    recurring,
    transactions,
)

web_router = APIRouter(include_in_schema=False)
web_router.include_router(pages.router)
web_router.include_router(transactions.router)
web_router.include_router(analytics.router)
web_router.include_router(recurring.router)
web_router.include_router(forecast.router)
web_router.include_router(recommendations.router)
web_router.include_router(imports.router)
web_router.include_router(categories.router)
web_router.include_router(categorization.router)
