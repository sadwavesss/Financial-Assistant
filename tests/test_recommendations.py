"""Recommendations: facts from the database, rule chains, explanations, API and pages."""

import datetime as dt
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.knowledge import load_recommendation_rules
from app.models import CategorySource, Transaction, TransactionType
from app.services.recommendations import build_recommendations, format_fact, render_template
from app.utils.dates import add_months
from tests.helpers import category_id

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME
TODAY = dt.date(2026, 11, 20)
OCTOBER = dt.date(2026, 10, 1)


def add(db: Session, day: dt.date, kind: TransactionType, amount: str, category: str) -> None:
    db.add(
        Transaction(
            date=day,
            type=kind,
            amount=Decimal(amount),
            amount_byn=Decimal(amount),
            description=category,
            category_id=category_id(db, category, kind),
            category_source=CategorySource.MANUAL,
        )
    )


def months_of(db: Session, income: str, groceries: str, cafe: str, count: int = 4) -> None:
    """Identical months July..October (or fewer) with the given amounts."""
    for back in range(count):
        month = add_months(OCTOBER, -back)
        add(db, month.replace(day=5), INCOME, income, "Зарплата")
        add(db, month.replace(day=10), EXPENSE, groceries, "Продукты")
        add(db, month.replace(day=15), EXPENSE, cafe, "Кафе и рестораны")


def ids(db: Session) -> list[str]:
    return [r.rule_id for r in build_recommendations(db, TODAY).recommendations]


def test_healthy_budget_gets_positive_feedback(seeded_db: Session) -> None:
    months_of(seeded_db, income="3000", groceries="900", cafe="300")
    seeded_db.commit()

    report = build_recommendations(seeded_db, TODAY)

    assert "R13_good_savings" in ids(seeded_db)
    assert "R2_deficit" not in ids(seeded_db)
    assert report.facts["savings_rate_avg"] == 0.6
    assert report.facts["month_label"] == "октябрь 2026"


def test_deficit_chain_leads_to_budget_risk(seeded_db: Session) -> None:
    months_of(seeded_db, income="1000", groceries="900", cafe="300")
    seeded_db.commit()

    report = build_recommendations(seeded_db, TODAY)

    found = [r.rule_id for r in report.recommendations]
    assert found[:2] == ["R1_budget_risk", "R2_deficit"]  # high severity first
    assert "R13_good_savings" not in found
    derived = [f.derived[0] for f in report.result.firings if f.derived]
    assert {"deficit", "low_savings", "budget_risk"} <= set(derived)
    # D1 and D2 (priorities 10, 11) derive facts that D5 (priority 14) uses in the same pass;
    # the second pass derives nothing new and ends the inference.
    assert report.result.passes == 2
    d5 = next(f for f in report.result.firings if f.rule.id == "D5_budget_risk")
    assert any(check.fact == "deficit" and check.passed for check in d5.checks)

    risk = report.recommendations[0]
    lines = [line.text for line in risk.explanation]
    assert any("выведено правилом D1_deficit" in line for line in lines)  # chain is explained
    deficit = report.recommendations[1]
    assert "200,00 BYN" in deficit.text  # 1200 spent - 1000 earned


def test_category_growth_and_wants_share(seeded_db: Session) -> None:
    months_of(seeded_db, income="3000", groceries="500", cafe="100", count=4)
    add(seeded_db, OCTOBER.replace(day=20), EXPENSE, "400", "Кафе и рестораны")  # October jump
    seeded_db.commit()

    report = build_recommendations(seeded_db, TODAY)

    growth = next(r for r in report.recommendations if r.rule_id == "R7_category_growth")
    assert growth.binding == "Кафе и рестораны"
    assert growth.title == "Рост расходов: Кафе и рестораны"
    assert "400%" in growth.text  # 500 in October vs 100 on average
    assert "R6_wants_share" in [r.rule_id for r in report.recommendations]  # 500 of 1000 = 50 %


def test_no_data_gives_no_recommendations(db: Session) -> None:
    report = build_recommendations(db, TODAY)

    assert report.recommendations == []
    assert "expense_month" not in report.facts


def test_formatting_and_templates() -> None:
    kb = load_recommendation_rules()

    assert format_fact(1234.5, "money") == "1\u00a0234,50 BYN"
    assert format_fact(0.256, "percent") == "26%"
    assert format_fact(["a", "b"], "list") == "a, b"
    assert format_fact(None, "money") == "нет данных"
    assert render_template(
        "{expense_month} / {x|percent}", kb, {"expense_month": 10, "x": 0.5}
    ) == ("10,00 BYN / 50%")
    assert render_template("{missing|money}", kb, {}) == "нет данных"


def test_api_and_pages(client: TestClient, seeded_db: Session) -> None:
    months_of(seeded_db, income="1000", groceries="900", cafe="300")
    seeded_db.commit()

    body = client.get("/api/recommendations").json()
    page = client.get("/recommendations")
    home = client.get("/")

    assert body["passes"] >= 1 and body["firings"]
    assert all({"rule_id", "severity", "explanation"} <= set(r) for r in body["recommendations"])
    assert "Протокол вывода" in page.text and "Почему?" in page.text
    assert home.status_code == 200


def test_empty_page(client: TestClient) -> None:
    assert "Недостаточно данных" in client.get("/recommendations").text
