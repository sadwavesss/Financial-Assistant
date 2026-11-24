"""REST API for the expense forecast."""

from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.forecast import ForecastOut
from app.services.analytics import Granularity
from app.services.forecast import build_forecast

router = APIRouter(prefix="/forecast", tags=["Прогноз"])


@router.get(
    "",
    response_model=ForecastOut,
    summary="Прогноз расходов",
    description=(
        "Три модели (скользящее среднее, линейная регрессия, сглаживание Хольта) сравниваются "
        "скользящим бэктестом на последних периодах; выбирается модель с наименьшей MAE. "
        "Горизонт: 1–6 месяцев или 1–12 недель."
    ),
)
def read_forecast(
    db: DbSession, granularity: Granularity = Granularity.MONTH, horizon: int | None = None
) -> ForecastOut:
    return ForecastOut.from_report(build_forecast(db, granularity, horizon))
