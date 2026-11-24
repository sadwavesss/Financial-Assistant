"""Expense forecast: builds time series from transactions and runs model selection.

- Only complete weeks/months are used for training: the current one is still in progress and
  would look like a sudden drop in spending. It becomes the first forecasted period, and the
  amount already spent in it is shown next to the forecast.
- Empty periods inside the history count as zero spending.
- The total and every major category are forecasted separately (each with its own best model),
  so category forecasts do not have to add up exactly to the total.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml.forecasting import ForecastResult, InsufficientHistoryError, forecast
from app.models import Category, Transaction, TransactionType
from app.services.analytics import Granularity, bucket_label, bucket_start, next_bucket
from app.services.errors import InvalidDataError

HORIZON_LIMITS = {Granularity.MONTH: (1, 6), Granularity.WEEK: (1, 12)}
DEFAULT_HORIZON = {Granularity.MONTH: 3, Granularity.WEEK: 4}
MAX_TEST_POINTS = {Granularity.MONTH: 4, Granularity.WEEK: 8}
UNCATEGORIZED = ("Без категории", "#adb5bd")


@dataclass(frozen=True)
class SeriesPoint:
    start: dt.date
    label: str
    value: float


@dataclass(frozen=True)
class ForecastedPoint:
    start: dt.date
    label: str
    value: float
    lower: float
    upper: float


@dataclass(frozen=True)
class CategoryForecast:
    category_id: int | None
    name: str
    color: str
    next_value: float  # forecast for the first future period
    total: float  # forecast for the whole horizon
    recent_average: float  # average of the last 3 complete periods
    model: str
    mae: float

    @property
    def change(self) -> float | None:
        if not self.recent_average:
            return None
        return self.next_value / self.recent_average - 1


@dataclass(frozen=True)
class ForecastReport:
    today: dt.date
    granularity: Granularity
    horizon: int
    history: list[SeriesPoint]
    points: list[ForecastedPoint]
    result: ForecastResult
    # The latest complete periods had no expenses at all: the data is probably not entered yet,
    # so the forecast starts after the last period with data, not at the current one.
    data_gap: bool
    current_spent: float  # already spent in the current (still incomplete) period
    current_elapsed: float  # share of the current period that has passed, 0..1
    categories: list[CategoryForecast]

    @property
    def total(self) -> float:
        return sum(point.value for point in self.points)

    @property
    def current_forecast(self) -> ForecastedPoint | None:
        """Forecast of the current period, if it is within the horizon."""
        current = bucket_start(self.today, self.granularity)
        return next((p for p in self.points if p.start == current), None)


def build_forecast(
    db: Session,
    granularity: Granularity = Granularity.MONTH,
    horizon: int | None = None,
    today: dt.date | None = None,
    category_limit: int = 8,
) -> ForecastReport:
    if granularity not in HORIZON_LIMITS:
        raise InvalidDataError("Прогноз строится по неделям или по месяцам.", field="granularity")
    low, high = HORIZON_LIMITS[granularity]
    horizon = horizon or DEFAULT_HORIZON[granularity]
    if not low <= horizon <= high:
        raise InvalidDataError(f"Горизонт прогноза — от {low} до {high}.", field="horizon")

    today = today or dt.date.today()
    current = bucket_start(today, granularity)
    starts = _history_starts(db, current, granularity)
    expenses = _expenses_by_bucket(db, starts[0] if starts else current, today, granularity)

    total_series = [float(sum(expenses.get(start, {}).values())) for start in starts]
    # Trailing periods without any expense mean "not entered yet", not "spent nothing":
    # they are dropped and the forecast starts right after the last period with data.
    while total_series and total_series[-1] == 0:
        total_series.pop()
        starts.pop()
    try:
        result = forecast(total_series, horizon, MAX_TEST_POINTS[granularity])
    except InsufficientHistoryError as exc:
        unit = "месяцев" if granularity is Granularity.MONTH else "недель"
        raise InvalidDataError(
            f"Для прогноза нужно не менее 6 полных {unit} истории расходов (сейчас {len(starts)})."
        ) from exc

    first_future = next_bucket(starts[-1], granularity)
    future, start = [], first_future
    for point in result.points:
        future.append(
            ForecastedPoint(
                start, bucket_label(start, granularity), point.value, point.lower, point.upper
            )
        )
        start = next_bucket(start, granularity)

    period_days = (next_bucket(current, granularity) - current).days
    return ForecastReport(
        today=today,
        granularity=granularity,
        horizon=horizon,
        history=[
            SeriesPoint(s, bucket_label(s, granularity), v)
            for s, v in zip(starts, total_series, strict=True)
        ],
        points=future,
        result=result,
        data_gap=first_future < current,
        current_spent=float(sum(expenses.get(current, {}).values())),
        current_elapsed=((today - current).days + 1) / period_days,
        categories=_category_forecasts(db, starts, expenses, horizon, granularity, category_limit),
    )


def _history_starts(db: Session, current: dt.date, granularity: Granularity) -> list[dt.date]:
    """Starts of all complete periods from the first expense up to (excluding) `current`."""
    first = db.scalar(
        select(func.min(Transaction.date)).where(Transaction.type == TransactionType.EXPENSE)
    )
    starts: list[dt.date] = []
    if first is None:
        return starts
    start = bucket_start(first, granularity)
    while start < current:
        starts.append(start)
        start = next_bucket(start, granularity)
    return starts


def _expenses_by_bucket(
    db: Session, since: dt.date, until: dt.date, granularity: Granularity
) -> dict[dt.date, dict[int | None, Decimal]]:
    rows = db.execute(
        select(Transaction.date, Transaction.category_id, Transaction.amount_byn).where(
            Transaction.type == TransactionType.EXPENSE, Transaction.date.between(since, until)
        )
    ).all()
    buckets: dict[dt.date, dict[int | None, Decimal]] = {}
    for day, category_id, amount in rows:
        bucket = buckets.setdefault(bucket_start(day, granularity), {})
        bucket[category_id] = bucket.get(category_id, Decimal(0)) + amount
    return buckets


def _category_forecasts(
    db: Session,
    starts: list[dt.date],
    expenses: dict[dt.date, dict[int | None, Decimal]],
    horizon: int,
    granularity: Granularity,
    limit: int,
) -> list[CategoryForecast]:
    totals: dict[int | None, Decimal] = {}
    for start in starts:
        for category_id, amount in expenses.get(start, {}).items():
            totals[category_id] = totals.get(category_id, Decimal(0)) + amount
    top = sorted(totals, key=lambda key: totals[key], reverse=True)[:limit]
    categories = {c.id: c for c in db.scalars(select(Category).where(Category.id.in_(top)))}

    forecasts = []
    for category_id in top:
        series = [float(expenses.get(start, {}).get(category_id, 0)) for start in starts]
        result = forecast(series, horizon, MAX_TEST_POINTS[granularity])
        category = categories.get(category_id)
        name, color = (category.name, category.color) if category else UNCATEGORIZED
        forecasts.append(
            CategoryForecast(
                category_id=category_id,
                name=name,
                color=color,
                next_value=result.points[0].value,
                total=sum(point.value for point in result.points),
                recent_average=sum(series[-3:]) / len(series[-3:]),
                model=result.best.label,
                mae=result.best.mae,
            )
        )
    return forecasts
