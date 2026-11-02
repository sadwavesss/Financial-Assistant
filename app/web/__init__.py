"""Server-rendered HTML pages."""

from fastapi import APIRouter

from app.web import imports, pages, transactions

web_router = APIRouter(include_in_schema=False)
web_router.include_router(pages.router)
web_router.include_router(transactions.router)
web_router.include_router(imports.router)
