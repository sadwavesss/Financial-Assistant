"""REST API for recurring payments and incomes."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.schemas.recurring import RecurringReportOut
from app.services.recurring import find_recurring

router = APIRouter(prefix="/recurring", tags=["Регулярные платежи"])


@router.get(
    "",
    response_model=RecurringReportOut,
    summary="Повторяющиеся платежи и доходы",
    description=(
        "Группы операций с регулярным интервалом (неделя, месяц, квартал, год) и стабильной "
        "суммой за последние `months` месяцев, с прогнозом даты следующего платежа."
    ),
)
def read_recurring(
    db: DbSession, months: Annotated[int, Query(ge=2, le=36)] = 12
) -> RecurringReportOut:
    return RecurringReportOut.from_report(find_recurring(db, months))
