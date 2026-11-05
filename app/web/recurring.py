"""HTML page of recurring payments and incomes."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.dependencies import DbSession
from app.models import TransactionType
from app.services.recurring import PERIODICITY_LABELS, find_recurring
from app.web.templating import templates

router = APIRouter(prefix="/recurring")
MONTH_OPTIONS = (6, 12, 24)


@router.get("", response_class=HTMLResponse)
def recurring_page(
    request: Request, db: DbSession, months: Annotated[int, Query(ge=2, le=36)] = 12
) -> HTMLResponse:
    report = find_recurring(db, months)
    return templates.TemplateResponse(
        request,
        "recurring/index.html",
        {
            "active_page": "recurring",
            "report": report,
            "expenses": report.of_type(TransactionType.EXPENSE),
            "incomes": report.of_type(TransactionType.INCOME),
            "stopped": [p for p in report.payments if not p.active],
            "upcoming": report.upcoming(30),
            "periodicity_labels": PERIODICITY_LABELS,
            "month_options": MONTH_OPTIONS,
        },
    )
