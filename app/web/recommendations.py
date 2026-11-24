"""HTML page of budget recommendations with explanations and the inference protocol."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.dependencies import DbSession
from app.services.recommendations import build_recommendations
from app.web.templating import templates

router = APIRouter(prefix="/recommendations")


@router.get("", response_class=HTMLResponse)
def recommendations_page(request: Request, db: DbSession) -> HTMLResponse:
    report = build_recommendations(db)
    return templates.TemplateResponse(
        request,
        "recommendations/index.html",
        {"active_page": "recommendations", "report": report},
    )
