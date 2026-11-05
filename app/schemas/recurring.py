"""Schemas of the recurring payments API."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.models import Currency, TransactionType
from app.services.recurring import Periodicity, RecurringPayment, RecurringReport


class RecurringPaymentOut(BaseModel):
    name: str
    type: TransactionType
    currency: Currency
    category: str | None
    periodicity: Periodicity
    count: int
    first_date: dt.date
    last_date: dt.date
    median_interval: float
    regularity: float
    amount_variation: float
    fixed_amount: bool
    typical_amount: Decimal
    typical_amount_byn: Decimal
    monthly_cost_byn: Decimal
    next_date: dt.date
    active: bool

    @classmethod
    def from_payment(cls, p: RecurringPayment) -> "RecurringPaymentOut":
        return cls(
            name=p.name,
            type=p.type,
            currency=p.currency,
            category=p.category.name if p.category else None,
            periodicity=p.periodicity,
            count=p.count,
            first_date=p.first_date,
            last_date=p.last_date,
            median_interval=p.median_interval,
            regularity=p.regularity,
            amount_variation=p.amount_variation,
            fixed_amount=p.fixed_amount,
            typical_amount=p.typical_amount,
            typical_amount_byn=p.typical_amount_byn,
            monthly_cost_byn=p.monthly_cost_byn,
            next_date=p.next_date,
            active=p.active,
        )


class RecurringReportOut(BaseModel):
    months: int
    average_monthly_expense: Decimal
    monthly_recurring_expense: Decimal
    recurring_share: float | None
    payments: list[RecurringPaymentOut]

    @classmethod
    def from_report(cls, report: RecurringReport) -> "RecurringReportOut":
        return cls(
            months=report.months,
            average_monthly_expense=report.average_monthly_expense,
            monthly_recurring_expense=report.monthly_recurring_expense,
            recurring_share=report.recurring_share,
            payments=[RecurringPaymentOut.from_payment(p) for p in report.payments],
        )
