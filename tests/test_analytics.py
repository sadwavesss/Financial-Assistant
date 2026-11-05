"""Analytics: periods, summary, structure, dynamics, comparison with the previous period."""

import datetime as dt
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import CategorySource, Transaction, TransactionType
from app.services.analytics import (
    Granularity,
    Period,
    PeriodPreset,
    auto_granularity,
    build_report,
    resolve_period,
)
from app.services.errors import InvalidDataError
from tests.helpers import category_id

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME
TODAY = dt.date(2026, 11, 5)
OCTOBER = Period(dt.date(2026, 10, 1), dt.date(2026, 10, 31))


def add(db: Session, day: str, kind: TransactionType, amount: str, category: str | None = None):
    db.add(
        Transaction(
            date=dt.date.fromisoformat(day),
            type=kind,
            amount=Decimal(amount),
            amount_byn=Decimal(amount),
            description=category or "без категории",
            category_id=category_id(db, category, kind) if category else None,
            category_source=CategorySource.MANUAL if category else None,
        )
    )


@pytest.fixture
def data(seeded_db: Session) -> Session:
    # September (previous period for October)
    add(seeded_db, "2026-09-05", INCOME, "2000", "Зарплата")
    add(seeded_db, "2026-09-10", EXPENSE, "200", "Продукты")
    add(seeded_db, "2026-09-12", EXPENSE, "100", "Кафе и рестораны")
    # October
    add(seeded_db, "2026-10-05", INCOME, "2000", "Зарплата")
    add(seeded_db, "2026-10-25", INCOME, "150", "Стипендия")
    add(seeded_db, "2026-10-02", EXPENSE, "300", "Продукты")
    add(seeded_db, "2026-10-20", EXPENSE, "100", "Продукты")
    add(seeded_db, "2026-10-15", EXPENSE, "50", "Кафе и рестораны")
    add(seeded_db, "2026-10-31", EXPENSE, "50", None)
    # Outside of both periods
    add(seeded_db, "2026-11-01", EXPENSE, "999", "Продукты")
    seeded_db.commit()
    return seeded_db


@pytest.mark.parametrize(
    ("preset", "start", "end"),
    [
        (PeriodPreset.MONTH, "2026-11-01", "2026-11-05"),
        (PeriodPreset.PREV_MONTH, "2026-10-01", "2026-10-31"),
        (PeriodPreset.MONTHS_3, "2026-09-01", "2026-11-05"),
        (PeriodPreset.MONTHS_12, "2025-12-01", "2026-11-05"),
        (PeriodPreset.YEAR, "2026-01-01", "2026-11-05"),
    ],
)
def test_presets(db: Session, preset: PeriodPreset, start: str, end: str) -> None:
    period = resolve_period(db, preset, today=TODAY)

    assert (period.start.isoformat(), period.end.isoformat()) == (start, end)


def test_all_time_covers_history(data: Session) -> None:
    period = resolve_period(data, PeriodPreset.ALL, today=TODAY)

    assert (period.start, period.end) == (dt.date(2026, 9, 5), TODAY)


def test_custom_period_validation(db: Session) -> None:
    with pytest.raises(InvalidDataError):
        resolve_period(db, PeriodPreset.CUSTOM)
    with pytest.raises(InvalidDataError):
        resolve_period(db, PeriodPreset.CUSTOM, dt.date(2026, 10, 2), dt.date(2026, 10, 1))


def test_previous_period_has_the_same_length() -> None:
    previous = OCTOBER.previous()

    assert (previous.start, previous.end) == (dt.date(2026, 8, 31), dt.date(2026, 9, 30))
    assert previous.days == OCTOBER.days == 31


@pytest.mark.parametrize(("days", "expected"), [(31, "day"), (90, "week"), (180, "month")])
def test_auto_granularity(days: int, expected: str) -> None:
    period = Period(dt.date(2026, 1, 1), dt.date(2026, 1, 1) + dt.timedelta(days=days - 1))

    assert auto_granularity(period).value == expected


def test_summary_and_comparison(data: Session) -> None:
    report = build_report(data, OCTOBER)

    s, p = report.summary, report.previous_summary
    assert (s.income, s.expense, s.balance, s.count) == (
        Decimal("2150.00"), Decimal("500.00"), Decimal("1650.00"), 6,
    )  # fmt: skip
    assert s.savings_rate == pytest.approx(1650 / 2150)
    assert (p.income, p.expense) == (Decimal("2000.00"), Decimal("300.00"))
    assert report.change(s.expense, p.expense) == pytest.approx(500 / 300 - 1)
    assert report.average_daily_expense == Decimal("16.13")  # 500 / 31


def test_expense_structure(data: Session) -> None:
    structure = build_report(data, OCTOBER).expense_structure

    assert [(i.name, i.amount, i.count) for i in structure] == [
        ("Продукты", Decimal("400.00"), 2),
        ("Кафе и рестораны", Decimal("50.00"), 1),
        ("Без категории", Decimal("50.00"), 1),
    ]
    assert sum(item.share for item in structure) == pytest.approx(1)
    groceries, cafe, uncategorized = structure
    assert groceries.change == pytest.approx(1.0)  # 400 vs 200
    assert cafe.change == pytest.approx(-0.5)  # 50 vs 100
    assert uncategorized.change is None  # nothing before


def test_dynamics_fills_empty_buckets(data: Session) -> None:
    daily = build_report(data, OCTOBER, Granularity.DAY).dynamics
    weekly = build_report(data, OCTOBER, Granularity.WEEK).dynamics
    two_months = Period(dt.date(2026, 9, 1), dt.date(2026, 10, 31))
    monthly = build_report(data, two_months, Granularity.MONTH).dynamics

    assert len(daily) == 31 and daily[1].expense == Decimal("300.00") and daily[0].expense == 0
    assert weekly[0].start == dt.date(2026, 9, 28)  # Monday of the week with October 1
    assert sum(b.expense for b in weekly) == Decimal("500.00")
    assert [(b.label, b.income, b.expense) for b in monthly] == [
        ("сен 2026", Decimal("2000.00"), Decimal("300.00")),
        ("окт 2026", Decimal("2150.00"), Decimal("500.00")),
    ]


def test_top_expenses(data: Session) -> None:
    top = build_report(data, OCTOBER, top=2).top_expenses

    assert [t.amount_byn for t in top] == [Decimal("300.00"), Decimal("100.00")]


def test_empty_period(db: Session) -> None:
    report = build_report(db, OCTOBER)

    assert report.summary.count == 0
    assert report.summary.savings_rate is None
    assert report.expense_structure == []
    assert report.change(report.summary.expense, report.previous_summary.expense) is None


def test_api(client: TestClient, data: Session) -> None:
    body = client.get(
        "/api/analytics",
        params={"period": "custom", "date_from": "2026-10-01", "date_to": "2026-10-31"},
    ).json()

    assert body["summary"]["expense"] == "500.00"
    assert body["expense_change"] == pytest.approx(2 / 3)
    assert body["expense_structure"][0]["name"] == "Продукты"
    assert len(body["dynamics"]) == 31


def test_api_rejects_custom_without_dates(client: TestClient) -> None:
    assert client.get("/api/analytics", params={"period": "custom"}).status_code == 422


def test_pages(client: TestClient, data: Session) -> None:
    analytics = client.get(
        "/analytics",
        params={"period": "custom", "date_from": "2026-10-01", "date_to": "2026-10-31"},
    )
    broken = client.get("/analytics", params={"period": "custom"})
    home = client.get("/")

    assert "Структура расходов" in analytics.text
    assert 'id="analytics-data"' in analytics.text  # chart data is embedded as JSON
    assert '"values": [400.0, 50.0, 50.0]' in analytics.text
    assert "Укажите начало и конец периода" in broken.text
    assert "Этот месяц" in home.text
