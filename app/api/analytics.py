"""REST API for financial analytics."""

import datetime as dt

from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.analytics import AnalyticsOut
from app.services.analytics import Granularity, PeriodPreset, build_report, resolve_period

router = APIRouter(prefix="/analytics", tags=["Аналитика"])


@router.get(
    "",
    response_model=AnalyticsOut,
    summary="Анализ доходов и расходов за период",
    description=(
        "Сводка, структура по категориям, динамика и крупнейшие расходы; "
        "все показатели сравниваются с предыдущим периодом той же длины. "
        "Для period=custom укажите date_from и date_to."
    ),
)
def read_analytics(
    db: DbSession,
    period: PeriodPreset = PeriodPreset.MONTHS_6,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    granularity: Granularity | None = None,
) -> AnalyticsOut:
    resolved = resolve_period(db, period, date_from, date_to)
    return AnalyticsOut.from_report(build_report(db, resolved, granularity))
