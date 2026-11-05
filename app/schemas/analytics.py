"""Schemas of the analytics API."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.services.analytics import AnalyticsReport, CategoryShare, Granularity


class PeriodOut(BaseModel):
    start: dt.date
    end: dt.date
    days: int


class SummaryOut(BaseModel):
    income: Decimal
    expense: Decimal
    balance: Decimal
    savings_rate: float | None
    count: int


class CategoryShareOut(BaseModel):
    category_id: int | None
    name: str
    color: str
    amount: Decimal
    share: float
    count: int
    previous_amount: Decimal
    change: float | None


class BucketOut(BaseModel):
    start: dt.date
    label: str
    income: Decimal
    expense: Decimal
    balance: Decimal


class TopExpenseOut(BaseModel):
    id: int
    date: dt.date
    description: str
    amount_byn: Decimal
    category: str | None


class AnalyticsOut(BaseModel):
    period: PeriodOut
    previous_period: PeriodOut
    granularity: Granularity
    summary: SummaryOut
    previous_summary: SummaryOut
    average_daily_expense: Decimal
    income_change: float | None
    expense_change: float | None
    expense_structure: list[CategoryShareOut]
    income_structure: list[CategoryShareOut]
    dynamics: list[BucketOut]
    top_expenses: list[TopExpenseOut]

    @classmethod
    def from_report(cls, report: AnalyticsReport) -> "AnalyticsOut":
        def period(p) -> PeriodOut:
            return PeriodOut(start=p.start, end=p.end, days=p.days)

        def summary(s) -> SummaryOut:
            return SummaryOut(
                income=s.income,
                expense=s.expense,
                balance=s.balance,
                savings_rate=s.savings_rate,
                count=s.count,
            )

        def share(item: CategoryShare) -> CategoryShareOut:
            return CategoryShareOut(
                category_id=item.category_id,
                name=item.name,
                color=item.color,
                amount=item.amount,
                share=item.share,
                count=item.count,
                previous_amount=item.previous_amount,
                change=item.change,
            )

        current, before = report.summary, report.previous_summary
        return cls(
            period=period(report.period),
            previous_period=period(report.previous_period),
            granularity=report.granularity,
            summary=summary(current),
            previous_summary=summary(before),
            average_daily_expense=report.average_daily_expense,
            income_change=report.change(current.income, before.income),
            expense_change=report.change(current.expense, before.expense),
            expense_structure=[share(item) for item in report.expense_structure],
            income_structure=[share(item) for item in report.income_structure],
            dynamics=[
                BucketOut(
                    start=b.start,
                    label=b.label,
                    income=b.income,
                    expense=b.expense,
                    balance=b.balance,
                )
                for b in report.dynamics
            ],
            top_expenses=[
                TopExpenseOut(
                    id=t.id,
                    date=t.date,
                    description=t.description,
                    amount_byn=t.amount_byn,
                    category=t.category.name if t.category else None,
                )
                for t in report.top_expenses
            ],
        )
