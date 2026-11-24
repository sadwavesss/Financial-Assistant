"""HTML page of the expense forecast."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError

from app.dependencies import DbSession
from app.services.analytics import Granularity
from app.services.errors import InvalidDataError
from app.services.forecast import DEFAULT_HORIZON, HORIZON_LIMITS, ForecastReport, build_forecast
from app.web.forms import clean_form
from app.web.templating import templates

router = APIRouter(prefix="/forecast")


class ForecastFilters(BaseModel):
    granularity: Granularity = Granularity.MONTH
    horizon: int | None = None


@router.get("", response_class=HTMLResponse)
def forecast_page(request: Request, db: DbSession) -> HTMLResponse:
    report, error = None, None
    try:
        filters = ForecastFilters.model_validate(clean_form(request.query_params))
    except ValidationError:
        filters = ForecastFilters()
    try:
        report = build_forecast(db, filters.granularity, filters.horizon)
    except InvalidDataError as exc:
        error = exc.message

    return templates.TemplateResponse(
        request,
        "forecast/index.html",
        {
            "active_page": "forecast",
            "report": report,
            "error": error,
            "granularity": filters.granularity,
            "horizon": filters.horizon or DEFAULT_HORIZON.get(filters.granularity, 3),
            "limits": {g.value: HORIZON_LIMITS[g] for g in HORIZON_LIMITS},
            "chart_data": chart_data(report) if report else None,
        },
    )


def chart_data(report: ForecastReport) -> dict:
    """History + forecast on one axis; the forecast line starts at the last actual value."""
    history, points = report.history, report.points
    labels = [p.label for p in history] + [p.label for p in points]
    gap = [None] * (len(history) - 1)
    return {
        "labels": labels,
        "actual": [round(p.value, 2) for p in history] + [None] * len(points),
        "forecast": gap + [round(history[-1].value, 2)] + [round(p.value, 2) for p in points],
        "lower": gap + [round(history[-1].value, 2)] + [round(p.lower, 2) for p in points],
        "upper": gap + [round(history[-1].value, 2)] + [round(p.upper, 2) for p in points],
    }
