"""Detection of recurring payments and incomes (subscriptions, mobile, utilities, salary).

1. Transactions of the look-back window are grouped by a "merchant key": type, currency and
   the description without digits and punctuation ("Заказ №123" and "Заказ №456" match).
2. A group of at least MIN_OCCURRENCES operations is periodic if the median interval between
   its dates fits a known period (week, month, quarter, year) and at least MIN_REGULARITY of
   the intervals lie within that period's tolerance.
3. The amount must be stable: coefficient of variation (std / mean) <= MAX_AMOUNT_VARIATION;
   up to FIXED_AMOUNT_VARIATION it is a fixed amount (a subscription), otherwise variable
   (utilities).
4. The next date is the last date plus the period; a payment overdue by more than the
   tolerance is considered stopped.
"""

import datetime as dt
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Category, Currency, Transaction, TransactionType
from app.utils.dates import add_months
from app.utils.text import normalize_text

MIN_OCCURRENCES = 3
MIN_REGULARITY = 0.75
MAX_AMOUNT_VARIATION = 0.35
FIXED_AMOUNT_VARIATION = 0.05
DAYS_IN_MONTH = Decimal("30.44")
CENT = Decimal("0.01")
_NOT_LETTERS = re.compile(r"[^a-zа-я]+")


class Periodicity(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass(frozen=True)
class PeriodRule:
    days: int  # nominal length
    tolerance: int  # allowed deviation of one interval, days
    months: int  # calendar months to add for the next date (0 = add days)
    per_month: Decimal  # how many payments fall on one month on average


PERIODS = {
    Periodicity.WEEKLY: PeriodRule(7, 2, 0, DAYS_IN_MONTH / 7),
    Periodicity.MONTHLY: PeriodRule(30, 4, 1, Decimal(1)),
    Periodicity.QUARTERLY: PeriodRule(91, 10, 3, Decimal(1) / 3),
    Periodicity.YEARLY: PeriodRule(365, 20, 12, Decimal(1) / 12),
}
PERIODICITY_LABELS = {
    Periodicity.WEEKLY: "еженедельно",
    Periodicity.MONTHLY: "ежемесячно",
    Periodicity.QUARTERLY: "ежеквартально",
    Periodicity.YEARLY: "ежегодно",
}


@dataclass(frozen=True)
class RecurringPayment:
    key: str
    name: str  # the latest original description
    type: TransactionType
    currency: Currency
    category: Category | None
    periodicity: Periodicity
    count: int
    first_date: dt.date
    last_date: dt.date
    median_interval: float  # days
    regularity: float  # share of intervals within tolerance, 0..1
    amount_variation: float  # coefficient of variation of amounts
    typical_amount: Decimal  # in the payment's currency (median of the last 3)
    typical_amount_byn: Decimal
    next_date: dt.date
    active: bool

    @property
    def fixed_amount(self) -> bool:
        return self.amount_variation <= FIXED_AMOUNT_VARIATION

    @property
    def monthly_cost_byn(self) -> Decimal:
        """Equivalent cost per month: weekly 10 BYN -> 43.49, quarterly 30 BYN -> 10.00."""
        per_month = PERIODS[self.periodicity].per_month
        return (self.typical_amount_byn * per_month).quantize(CENT, ROUND_HALF_UP)

    def days_until_next(self, today: dt.date) -> int:
        return (self.next_date - today).days


@dataclass(frozen=True)
class RecurringReport:
    today: dt.date
    months: int
    payments: list[RecurringPayment]
    average_monthly_expense: Decimal  # all expenses of the window, per month

    def of_type(self, kind: TransactionType, active: bool = True) -> list[RecurringPayment]:
        return [p for p in self.payments if p.type is kind and p.active is active]

    @property
    def monthly_recurring_expense(self) -> Decimal:
        return sum(
            (p.monthly_cost_byn for p in self.of_type(TransactionType.EXPENSE)), Decimal("0.00")
        )

    @property
    def recurring_share(self) -> float | None:
        """Share of the average monthly expenses taken by active recurring payments."""
        if not self.average_monthly_expense:
            return None
        return float(self.monthly_recurring_expense / self.average_monthly_expense)

    def upcoming(self, days: int = 30) -> list[RecurringPayment]:
        """Active payments and incomes expected within `days` (overdue ones included)."""
        horizon = self.today + dt.timedelta(days=days)
        due = [p for p in self.payments if p.active and p.next_date <= horizon]
        return sorted(due, key=lambda p: p.next_date)


def merchant_key(description: str) -> str:
    """'OPENAI *CHATGPT SUBSCR 0425' -> 'openai chatgpt subscr'; digits and signs are dropped."""
    return _NOT_LETTERS.sub(" ", normalize_text(description)).strip()


def find_recurring(db: Session, months: int = 12, today: dt.date | None = None) -> RecurringReport:
    today = today or dt.date.today()
    start = add_months(today, -months)
    transactions = list(
        db.scalars(
            select(Transaction)
            .options(selectinload(Transaction.category))
            .where(Transaction.date.between(start, today))
            .order_by(Transaction.date, Transaction.id)
        )
    )

    groups: dict[tuple[TransactionType, Currency, str], list[Transaction]] = defaultdict(list)
    for transaction in transactions:
        key = merchant_key(transaction.description)
        if key:
            groups[(transaction.type, transaction.currency, key)].append(transaction)

    payments = [
        payment
        for (kind, currency, key), items in groups.items()
        if (payment := _analyze(key, kind, currency, items, today)) is not None
    ]
    payments.sort(key=lambda p: (not p.active, -p.monthly_cost_byn))

    return RecurringReport(today, months, payments, _average_monthly_expense(transactions, today))


def _average_monthly_expense(transactions: list[Transaction], today: dt.date) -> Decimal:
    """Expenses per month over the period actually covered by data (not the whole window)."""
    expenses = [t for t in transactions if t.type is TransactionType.EXPENSE]
    if not expenses:
        return Decimal("0.00")
    covered_days = (today - expenses[0].date).days + 1
    months_covered = max(Decimal(1), Decimal(covered_days) / DAYS_IN_MONTH)
    total = sum((t.amount_byn for t in expenses), Decimal(0))
    return (total / months_covered).quantize(CENT, ROUND_HALF_UP)


def _analyze(
    key: str,
    kind: TransactionType,
    currency: Currency,
    items: list[Transaction],
    today: dt.date,
) -> RecurringPayment | None:
    dates = sorted({t.date for t in items})  # several payments on one day count once
    if len(dates) < MIN_OCCURRENCES:
        return None

    intervals = [(later - earlier).days for earlier, later in pairwise(dates)]
    median_interval = statistics.median(intervals)
    periodicity = _match_period(median_interval)
    if periodicity is None:
        return None
    rule = PERIODS[periodicity]
    regularity = sum(abs(i - rule.days) <= rule.tolerance for i in intervals) / len(intervals)
    if regularity < MIN_REGULARITY:
        return None

    amounts = [float(t.amount) for t in items]
    mean = statistics.fmean(amounts)
    variation = statistics.pstdev(amounts) / mean if mean else 0.0
    if variation > MAX_AMOUNT_VARIATION:
        return None

    recent = items[-3:]
    last_date = dates[-1]
    next_date = _next_date(last_date, rule)
    categories = Counter(t.category_id for t in items if t.category_id is not None)
    category_id = categories.most_common(1)[0][0] if categories else None
    return RecurringPayment(
        key=key,
        name=items[-1].description,
        type=kind,
        currency=currency,
        category=next((t.category for t in items if t.category_id == category_id), None),
        periodicity=periodicity,
        count=len(items),
        first_date=dates[0],
        last_date=last_date,
        median_interval=float(median_interval),
        regularity=round(regularity, 3),
        amount_variation=round(variation, 3),
        typical_amount=_median([t.amount for t in recent]),
        typical_amount_byn=_median([t.amount_byn for t in recent]),
        next_date=next_date,
        active=(today - next_date).days <= rule.tolerance,
    )


def _match_period(median_interval: float) -> Periodicity | None:
    for periodicity, rule in PERIODS.items():
        if abs(median_interval - rule.days) <= rule.tolerance:
            return periodicity
    return None


def _next_date(last: dt.date, rule: PeriodRule) -> dt.date:
    if rule.months:
        return add_months(last, rule.months)
    return last + dt.timedelta(days=rule.days)


def _median(values: list[Decimal]) -> Decimal:
    return Decimal(statistics.median(values)).quantize(CENT, ROUND_HALF_UP)
