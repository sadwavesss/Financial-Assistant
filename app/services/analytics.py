"""Financial analytics for a period: summary, structure, dynamics and top expenses.

All amounts are in BYN (`Transaction.amount_byn`). Every indicator is also calculated for the
previous period of the same length, so changes can be shown ("expenses +12 % vs. before").
"""

import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionType
from app.services.errors import InvalidDataError
from app.utils.dates import add_months

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
UNCATEGORIZED_NAME = "Без категории"
UNCATEGORIZED_COLOR = "#adb5bd"


class PeriodPreset(StrEnum):
    MONTH = "month"  # current month up to today
    PREV_MONTH = "prev_month"  # previous calendar month
    MONTHS_3 = "3m"  # current month and two previous ones
    MONTHS_6 = "6m"
    MONTHS_12 = "12m"
    YEAR = "year"  # since January 1
    ALL = "all"  # whole history
    CUSTOM = "custom"


PERIOD_LABELS = {
    PeriodPreset.MONTH: "Этот месяц",
    PeriodPreset.PREV_MONTH: "Прошлый месяц",
    PeriodPreset.MONTHS_3: "3 месяца",
    PeriodPreset.MONTHS_6: "6 месяцев",
    PeriodPreset.MONTHS_12: "12 месяцев",
    PeriodPreset.YEAR: "С начала года",
    PeriodPreset.ALL: "Всё время",
    PeriodPreset.CUSTOM: "Свой период",
}


class Granularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


GRANULARITY_LABELS = {Granularity.DAY: "По дням", Granularity.WEEK: "По неделям",
                      Granularity.MONTH: "По месяцам"}  # fmt: skip


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> "Period":
        """The period of the same length right before this one."""
        end = self.start - dt.timedelta(days=1)
        return Period(end - dt.timedelta(days=self.days - 1), end)


@dataclass(frozen=True)
class Summary:
    income: Decimal
    expense: Decimal
    count: int

    @property
    def balance(self) -> Decimal:
        return self.income - self.expense

    @property
    def savings_rate(self) -> float | None:
        """Share of income that was not spent; None without income."""
        return float(self.balance / self.income) if self.income else None


@dataclass(frozen=True)
class CategoryShare:
    category_id: int | None
    name: str
    color: str
    amount: Decimal
    share: float  # 0..1 of the type's total in the period
    count: int
    previous_amount: Decimal

    @property
    def change(self) -> float | None:
        """Relative change vs. the previous period; None if there was nothing before."""
        if not self.previous_amount:
            return None
        return float((self.amount - self.previous_amount) / self.previous_amount)


@dataclass(frozen=True)
class Bucket:
    start: dt.date
    label: str
    income: Decimal
    expense: Decimal

    @property
    def balance(self) -> Decimal:
        return self.income - self.expense


@dataclass(frozen=True)
class AnalyticsReport:
    period: Period
    previous_period: Period
    granularity: Granularity
    summary: Summary
    previous_summary: Summary
    expense_structure: list[CategoryShare]
    income_structure: list[CategoryShare]
    dynamics: list[Bucket]
    top_expenses: list[Transaction]

    @property
    def average_daily_expense(self) -> Decimal:
        return (self.summary.expense / self.period.days).quantize(CENT, ROUND_HALF_UP)

    @staticmethod
    def change(current: Decimal, previous: Decimal) -> float | None:
        return float((current - previous) / previous) if previous else None


# ---------- Period selection ----------


def resolve_period(
    db: Session,
    preset: PeriodPreset,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    today: dt.date | None = None,
) -> Period:
    today = today or dt.date.today()
    month_start = today.replace(day=1)
    if preset is PeriodPreset.CUSTOM:
        if date_from is None or date_to is None:
            raise InvalidDataError("Укажите начало и конец периода.", field="date_from")
        if date_from > date_to:
            raise InvalidDataError("Начало периода позже его конца.", field="date_from")
        return Period(date_from, date_to)
    if preset is PeriodPreset.PREV_MONTH:
        end = month_start - dt.timedelta(days=1)
        return Period(end.replace(day=1), end)
    if preset is PeriodPreset.YEAR:
        return Period(today.replace(month=1, day=1), today)
    if preset is PeriodPreset.ALL:
        first, last = db.execute(
            select(func.min(Transaction.date), func.max(Transaction.date))
        ).one()
        return Period(first or today, max(last or today, today))
    months_back = {PeriodPreset.MONTH: 0, PeriodPreset.MONTHS_3: 2, PeriodPreset.MONTHS_6: 5,
                   PeriodPreset.MONTHS_12: 11}[preset]  # fmt: skip
    return Period(add_months(month_start, -months_back), today)


def auto_granularity(period: Period) -> Granularity:
    if period.days <= 31:
        return Granularity.DAY
    if period.days <= 120:
        return Granularity.WEEK
    return Granularity.MONTH


# ---------- Report ----------


def build_report(
    db: Session, period: Period, granularity: Granularity | None = None, top: int = 5
) -> AnalyticsReport:
    granularity = granularity or auto_granularity(period)
    previous = period.previous()
    return AnalyticsReport(
        period=period,
        previous_period=previous,
        granularity=granularity,
        summary=_summary(db, period),
        previous_summary=_summary(db, previous),
        expense_structure=_structure(db, period, previous, TransactionType.EXPENSE),
        income_structure=_structure(db, period, previous, TransactionType.INCOME),
        dynamics=_dynamics(db, period, granularity),
        top_expenses=_top_expenses(db, period, top),
    )


def _in_period(period: Period):
    return Transaction.date.between(period.start, period.end)


def _summary(db: Session, period: Period) -> Summary:
    rows = db.execute(
        select(Transaction.type, func.sum(Transaction.amount_byn), func.count())
        .where(_in_period(period))
        .group_by(Transaction.type)
    ).all()
    totals = {kind: (_money(amount), count) for kind, amount, count in rows}
    income, income_count = totals.get(TransactionType.INCOME, (ZERO, 0))
    expense, expense_count = totals.get(TransactionType.EXPENSE, (ZERO, 0))
    return Summary(income, expense, income_count + expense_count)


def _amounts_by_category(
    db: Session, period: Period, kind: TransactionType
) -> dict[int | None, tuple[Decimal, int]]:
    rows = db.execute(
        select(Transaction.category_id, func.sum(Transaction.amount_byn), func.count())
        .where(_in_period(period), Transaction.type == kind)
        .group_by(Transaction.category_id)
    ).all()
    return {category_id: (_money(amount), count) for category_id, amount, count in rows}


def _structure(
    db: Session, period: Period, previous: Period, kind: TransactionType
) -> list[CategoryShare]:
    current = _amounts_by_category(db, period, kind)
    before = _amounts_by_category(db, previous, kind)
    total = sum((amount for amount, _ in current.values()), ZERO)
    categories = {
        c.id: c for c in db.scalars(select(Category).where(Category.id.in_(list(current))))
    }
    shares = []
    for category_id, (amount, count) in current.items():
        category = categories.get(category_id)
        shares.append(
            CategoryShare(
                category_id=category_id,
                name=category.name if category else UNCATEGORIZED_NAME,
                color=category.color if category else UNCATEGORIZED_COLOR,
                amount=amount,
                share=float(amount / total) if total else 0.0,
                count=count,
                previous_amount=before.get(category_id, (ZERO, 0))[0],
            )
        )
    # Deterministic order: larger first; on equal amounts "Без категории" last, then by name.
    return sorted(shares, key=lambda i: (-i.amount, i.category_id is None, i.name))


def _dynamics(db: Session, period: Period, granularity: Granularity) -> list[Bucket]:
    rows = db.execute(
        select(Transaction.date, Transaction.type, Transaction.amount_byn).where(_in_period(period))
    ).all()
    sums: dict[dt.date, dict[TransactionType, Decimal]] = {}
    for day, kind, amount in rows:
        bucket = sums.setdefault(_bucket_start(day, granularity), {})
        bucket[kind] = bucket.get(kind, ZERO) + amount

    buckets = []
    start = _bucket_start(period.start, granularity)
    while start <= period.end:  # every bucket of the period, including empty ones
        values = sums.get(start, {})
        buckets.append(
            Bucket(
                start=start,
                label=_bucket_label(start, granularity),
                income=_money(values.get(TransactionType.INCOME)),
                expense=_money(values.get(TransactionType.EXPENSE)),
            )
        )
        start = _next_bucket(start, granularity)
    return buckets


def _top_expenses(db: Session, period: Period, limit: int) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(_in_period(period), Transaction.type == TransactionType.EXPENSE)
            .order_by(Transaction.amount_byn.desc(), Transaction.date.desc())
            .limit(limit)
        )
    )


# ---------- Date helpers ----------

MONTHS_SHORT = ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")


def _bucket_start(day: dt.date, granularity: Granularity) -> dt.date:
    if granularity is Granularity.WEEK:
        return day - dt.timedelta(days=day.weekday())  # Monday
    if granularity is Granularity.MONTH:
        return day.replace(day=1)
    return day


def _next_bucket(start: dt.date, granularity: Granularity) -> dt.date:
    if granularity is Granularity.WEEK:
        return start + dt.timedelta(days=7)
    if granularity is Granularity.MONTH:
        return add_months(start, 1)
    return start + dt.timedelta(days=1)


def _bucket_label(start: dt.date, granularity: Granularity) -> str:
    if granularity is Granularity.MONTH:
        return f"{MONTHS_SHORT[start.month - 1]} {start.year}"
    if granularity is Granularity.WEEK:
        return f"с {start:%d.%m}"
    return f"{start:%d.%m}"


def _money(value: Decimal | None) -> Decimal:
    return Decimal(value or 0).quantize(CENT, ROUND_HALF_UP)
