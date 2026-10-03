"""Application entry point: `uvicorn app.main:app --reload`."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import api_router
from app.config import STATIC_DIR, get_settings
from app.services.errors import ServiceError
from app.web import web_router
from app.web.templating import templates


async def service_error_handler(request: Request, exc: ServiceError) -> Response:
    """Business errors: JSON {"detail": {"code", "message"}} for the API, an HTML page otherwise."""
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_dict()})
    return templates.TemplateResponse(
        request, "error.html", {"message": exc.message}, status_code=exc.status_code
    )


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
    app.add_exception_handler(ServiceError, service_error_handler)
    return app


app = create_app()
