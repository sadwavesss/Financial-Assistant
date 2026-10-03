"""Server-rendered HTML pages."""

from fastapi import APIRouter

from app.web import pages

web_router = APIRouter(include_in_schema=False)
web_router.include_router(pages.router)
