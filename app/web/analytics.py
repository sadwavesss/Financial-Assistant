"""HTML dashboard of financial analytics."""

import datetime as dt

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from app.dependencies import DbSession
from app.services.analytics import (
    GRANULARITY_LABELS,
    PERIOD_LABELS,
    AnalyticsReport,
    Granularity,
    PeriodPreset,
    build_report,
    resolve_period,
)
from app.services.errors import InvalidDataError
from app.utils.validation import humanize_errors
from app.web.forms import clean_form
from app.web.templating import templates

router = APIRouter(prefix="/analytics")


class AnalyticsFilters(BaseModel):
    period: PeriodPreset = PeriodPreset.MONTHS_6
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    granularity: Granularity | None = None


@router.get("", response_class=HTMLResponse)
def analytics_page(request: Request, db: DbSession) -> HTMLResponse:
    raw = clean_form(request.query_params)
    error = None
    try:
        filters = AnalyticsFilters.model_validate(raw)
        period = resolve_period(db, filters.period, filters.date_from, filters.date_to)
    except ValidationError as exc:
        filters, error = AnalyticsFilters(), "; ".join(humanize_errors(exc).values())
        period = resolve_period(db, filters.period)
    except InvalidDataError as exc:
        filters, error = AnalyticsFilters(), exc.message
        period = resolve_period(db, filters.period)

    report = build_report(db, period, filters.granularity)
    return templates.TemplateResponse(
        request,
        "analytics/index.html",
        {
            "active_page": "analytics",
            "report": report,
            "filters": filters,
            "period_labels": PERIOD_LABELS,
            "granularity_labels": GRANULARITY_LABELS,
            "chart_data": chart_data(report),
            "error": error,
        },
    )


def chart_data(report: AnalyticsReport) -> dict:
    """Plain numbers for Chart.js (floats are fine for drawing; tables show exact Decimals)."""
    return {
        "structure": {
            "labels": [item.name for item in report.expense_structure],
            "values": [float(item.amount) for item in report.expense_structure],
            "colors": [item.color for item in report.expense_structure],
        },
        "dynamics": {
            "labels": [bucket.label for bucket in report.dynamics],
            "income": [float(bucket.income) for bucket in report.dynamics],
            "expense": [float(bucket.expense) for bucket in report.dynamics],
            "balance": [float(bucket.balance) for bucket in report.dynamics],
        },
    }
