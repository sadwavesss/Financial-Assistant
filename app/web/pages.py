"""General pages of the web interface."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.dependencies import DbSession
from app.services.analytics import PeriodPreset, build_report, resolve_period
from app.services.recommendations import build_recommendations
from app.services.recurring import find_recurring
from app.web.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: DbSession) -> HTMLResponse:
    """Home page: current month summary, top recommendations, nearest recurring payments."""
    report = build_report(db, resolve_period(db, PeriodPreset.MONTH), top=3)
    recurring = find_recurring(db)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "active_page": "index",
            "report": report,
            "upcoming": recurring.upcoming(14)[:5],
            "today": recurring.today,
            "recommendations": build_recommendations(db).recommendations[:3],
        },
    )
