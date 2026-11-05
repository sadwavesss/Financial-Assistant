"""Recurring payments: periodicity, amount stability, next date, status, demo data."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.importers.csv_importer import CsvImporter
from app.models import Currency, Transaction, TransactionType
from app.services.demo_data import generate_demo_rows, write_demo_csv
from app.services.imports import run_import
from app.services.recurring import Periodicity, find_recurring, merchant_key
from app.utils.dates import add_months

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME
TODAY = dt.date(2026, 11, 5)


def add(db: Session, day: dt.date, description: str, amount: str, **extra) -> None:
    db.add(
        Transaction(
            date=day,
            type=extra.get("kind", EXPENSE),
            amount=Decimal(amount),
            currency=extra.get("currency", Currency.BYN),
            amount_byn=Decimal(extra.get("amount_byn", amount)),
            description=description,
        )
    )


def monthly(db: Session, description: str, amounts: list[str], last: dt.date, **extra) -> None:
    for back, amount in enumerate(reversed(amounts)):
        add(db, add_months(last, -back), description, amount, **extra)


def names(db: Session, **kwargs) -> list[str]:
    return [p.name for p in find_recurring(db, today=TODAY, **kwargs).payments]


def test_merchant_key_ignores_digits_and_signs() -> None:
    assert merchant_key("OPENAI *CHATGPT SUBSCR 0425") == "openai chatgpt subscr"
    assert merchant_key("Заказ №123") == merchant_key("заказ 456") == "заказ"
    assert merchant_key("12345") == ""


def test_monthly_subscription_with_next_date(db: Session) -> None:
    monthly(db, "Яндекс Плюс", ["9.99"] * 6, dt.date(2026, 10, 3))
    db.commit()

    (payment,) = find_recurring(db, today=TODAY).payments

    assert payment.periodicity is Periodicity.MONTHLY
    assert (payment.count, payment.regularity, payment.fixed_amount) == (6, 1.0, True)
    assert payment.next_date == dt.date(2026, 11, 3)
    assert payment.active
    assert payment.monthly_cost_byn == Decimal("9.99")


def test_weekly_payment_and_its_monthly_cost(db: Session) -> None:
    for week in range(6):
        add(db, dt.date(2026, 10, 1) + dt.timedelta(days=7 * week), "Бассейн", "10")
    db.commit()

    (payment,) = find_recurring(db, today=TODAY).payments

    assert payment.periodicity is Periodicity.WEEKLY
    assert payment.monthly_cost_byn == Decimal("43.49")  # 10 * 30.44 / 7


def test_end_of_month_date_is_clamped() -> None:
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)


def test_variable_but_stable_amount_is_detected_as_variable(db: Session) -> None:
    monthly(db, "Оплата ЖКУ", ["95", "120", "140", "110"], dt.date(2026, 10, 10))
    db.commit()

    (payment,) = find_recurring(db, today=TODAY).payments

    assert not payment.fixed_amount
    assert payment.typical_amount == Decimal("120.00")  # median of the last three


def test_frequent_irregular_spending_is_not_recurring(db: Session) -> None:
    for offset in (0, 2, 3, 7, 8, 12, 15, 16, 21, 25):
        add(db, dt.date(2026, 10, 1) + dt.timedelta(days=offset), "Евроопт", "30")
    db.commit()

    assert names(db) == []


def test_irregular_intervals_are_rejected(db: Session) -> None:
    for day in ("2026-05-02", "2026-06-01", "2026-08-20", "2026-09-01", "2026-10-30"):
        add(db, dt.date.fromisoformat(day), "AliExpress", "15")
    db.commit()

    assert names(db) == []


def test_unstable_amount_is_rejected(db: Session) -> None:
    monthly(db, "Перевод другу", ["10", "200", "35", "500"], dt.date(2026, 10, 10))
    db.commit()

    assert names(db) == []


def test_two_payments_are_not_enough(db: Session) -> None:
    monthly(db, "Netflix", ["20", "20"], dt.date(2026, 10, 10))
    db.commit()

    assert names(db) == []


def test_stopped_subscription_is_inactive(db: Session) -> None:
    monthly(db, "Spotify", ["5"] * 5, dt.date(2026, 7, 15))
    db.commit()

    (payment,) = find_recurring(db, today=TODAY).payments

    assert not payment.active
    assert find_recurring(db, today=TODAY).monthly_recurring_expense == 0


def test_currencies_are_separate_and_amounts_compared_in_own_currency(db: Session) -> None:
    # The same 20 USD becomes a different BYN amount every month: still a fixed subscription.
    for back, byn in enumerate(["60.10", "61.40", "59.80", "62.00"]):
        add(db, add_months(dt.date(2026, 10, 18), -back), "OPENAI CHATGPT", "20",
            currency=Currency.USD, amount_byn=byn)  # fmt: skip
    db.commit()

    (payment,) = find_recurring(db, today=TODAY).payments

    assert (payment.currency, payment.fixed_amount) == (Currency.USD, True)
    assert payment.typical_amount == Decimal("20.00")


def test_share_of_monthly_expenses_and_upcoming(db: Session) -> None:
    monthly(db, "МТС", ["25"] * 4, dt.date(2026, 10, 12))
    monthly(db, "Зарплата", ["2000"] * 4, dt.date(2026, 10, 5), kind=INCOME)
    add(db, dt.date(2026, 10, 20), "Ноутбук", "1000")
    db.commit()

    report = find_recurring(db, today=TODAY)

    assert report.monthly_recurring_expense == Decimal("25.00")
    assert 0 < report.recurring_share < 1
    assert [p.name for p in report.upcoming(30)] == ["Зарплата", "МТС"]  # Nov 5, Nov 12


def test_demo_data_finds_exactly_the_generated_regular_payments(
    seeded_db: Session, providers, tmp_path: Path
) -> None:
    path = tmp_path / "demo.csv"
    write_demo_csv(generate_demo_rows(months=12, end=TODAY), path)
    run_import(seeded_db, path.read_bytes(), CsvImporter(), providers)

    found = set(names(seeded_db))

    # All monthly series of the generator except cashback, whose amount varies too much (3-15).
    assert found == {
        "Заработная плата ООО «Софтлайн»", "Аванс по заработной плате", "Стипендия БГУИР",
        "Оплата ЖКУ, ЕРИП", "МТС, мобильная связь", "BYFLY Белтелеком", "Проездной Минсктранс",
        "Яндекс Плюс", "OPENAI *CHATGPT SUBSCR", "APPLE.COM/BILL iCloud",
    }  # fmt: skip


def test_api_and_page(client: TestClient, db: Session) -> None:
    monthly(db, "Яндекс Плюс", ["9.99"] * 4, dt.date.today().replace(day=1))
    db.commit()

    body = client.get("/api/recurring").json()
    page = client.get("/recurring")
    home = client.get("/")

    assert body["payments"][0]["periodicity"] == "monthly"
    assert "Регулярные расходы" in page.text and "Яндекс Плюс" in page.text
    assert home.status_code == 200
    assert client.get("/api/recurring", params={"months": 1}).status_code == 422


@pytest.mark.parametrize("months", [6, 24])
def test_window_parameter(db: Session, months: int) -> None:
    assert find_recurring(db, months=months, today=TODAY).months == months
