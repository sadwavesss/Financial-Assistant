"""Application entry point: `uvicorn app.main:app --reload`."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import api_router
from app.config import STATIC_DIR, get_settings
from app.web import web_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
        description="REST API интеллектуального ассистента для анализа личных финансов.",
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(api_router, prefix="/api")
    app.include_router(web_router)
    return app


app = create_app()
