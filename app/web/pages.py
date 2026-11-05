"""General pages of the web interface."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.dependencies import DbSession
from app.services.analytics import PeriodPreset, build_report, resolve_period
from app.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: DbSession) -> HTMLResponse:
    """Home page with a short summary of the current month."""
    report = build_report(db, resolve_period(db, PeriodPreset.MONTH), top=3)
    return templates.TemplateResponse(
        request, "index.html", {"active_page": "index", "report": report}
    )
