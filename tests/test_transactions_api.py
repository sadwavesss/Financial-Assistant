"""REST API of transactions: validation, currency conversion, filters, update and delete."""

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.dependencies import get_rate_providers
from app.main import app
from app.models import TransactionType
from tests.helpers import FakeRateProvider, category_id

TODAY = dt.date.today()


def payload(**overrides: Any) -> dict[str, Any]:
    data = {
        "date": TODAY.isoformat(),
        "type": "expense",
        "amount": "25.40",
        "description": "Евроопт, продукты",
    }
    return {**data, **overrides}


def go_offline(offline_providers: list[FakeRateProvider]) -> None:
    app.dependency_overrides[get_rate_providers] = lambda: offline_providers


def test_create_byn_transaction(client: TestClient, seeded_db: Session) -> None:
    groceries = category_id(seeded_db, "Продукты", TransactionType.EXPENSE)

    response = client.post("/api/transactions", json=payload(category_id=groceries))

    assert response.status_code == 201
    body = response.json()
    assert body["amount_byn"] == "25.40"
    assert body["exchange_rate"] == "1.000000"
    assert body["rate_source"] is None
    assert body["category"]["name"] == "Продукты"
    assert body["category_source"] == "manual"


def test_create_usd_transaction_uses_online_rate(client: TestClient) -> None:
    response = client.post("/api/transactions", json=payload(currency="USD", amount="10"))

    body = response.json()
    assert response.status_code == 201
    assert (body["exchange_rate"], body["rate_source"]) == ("3.250000", "nbrb")
    assert body["amount_byn"] == "32.50"


def test_manual_rate(client: TestClient) -> None:
    response = client.post(
        "/api/transactions",
        json=payload(currency="USD", amount="10", rate_mode="manual", manual_rate="3.1"),
    )

    assert response.json()["rate_source"] == "manual"
    assert response.json()["amount_byn"] == "31.00"


def test_offline_returns_history_option_then_history_mode_works(
    client: TestClient, offline_providers: list[FakeRateProvider]
) -> None:
    yesterday = (TODAY - dt.timedelta(days=1)).isoformat()
    client.post(
        "/api/transactions",
        json=payload(date=yesterday, currency="USD", amount="5"),
    )
    go_offline(offline_providers)

    failed = client.post("/api/transactions", json=payload(currency="USD", amount="10"))
    assert failed.status_code == 422
    detail = failed.json()["detail"]
    assert detail["code"] == "rate_unavailable"
    assert detail["history"] == {
        "currency": "USD",
        "rate": "3.250000",
        "source": "nbrb",
        "date": yesterday,
    }

    created = client.post(
        "/api/transactions", json=payload(currency="USD", amount="10", rate_mode="history")
    )
    assert created.status_code == 201
    assert (created.json()["rate_source"], created.json()["amount_byn"]) == ("history", "32.50")


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"amount": "-3"},
        {"amount": "1.234"},
        {"date": (TODAY + dt.timedelta(days=1)).isoformat()},
        {"type": "transfer"},
        {"currency": "EUR"},
        {"currency": "USD", "rate_mode": "manual"},
        {"description": "x" * 256},
    ],
)
def test_invalid_input_is_rejected(client: TestClient, overrides: dict[str, Any]) -> None:
    assert client.post("/api/transactions", json=payload(**overrides)).status_code == 422


def test_category_must_match_transaction_type(client: TestClient, seeded_db: Session) -> None:
    salary = category_id(seeded_db, "Зарплата", TransactionType.INCOME)

    response = client.post("/api/transactions", json=payload(category_id=salary))

    assert response.status_code == 422
    assert response.json()["detail"]["field"] == "category_id"


def test_unknown_category_is_rejected(client: TestClient) -> None:
    response = client.post("/api/transactions", json=payload(category_id=999))

    assert response.status_code == 422


def test_list_filters_search_and_totals(client: TestClient, seeded_db: Session) -> None:
    week_ago = (TODAY - dt.timedelta(days=7)).isoformat()
    client.post("/api/transactions", json=payload(description="ЕВРООПТ Минск", amount="10"))
    client.post("/api/transactions", json=payload(description="Такси", amount="5", date=week_ago))
    client.post(
        "/api/transactions",
        json=payload(type="income", description="Зарплата", amount="1000"),
    )

    everything = client.get("/api/transactions").json()
    assert everything["total"] == 3
    assert (everything["income_byn"], everything["expense_byn"]) == ("1000.00", "15.00")

    # Case-insensitive search works for Cyrillic too.
    found = client.get("/api/transactions", params={"search": "евроопт"}).json()
    assert [item["description"] for item in found["items"]] == ["ЕВРООПТ Минск"]

    recent = client.get("/api/transactions", params={"date_from": TODAY.isoformat()}).json()
    assert recent["total"] == 2

    expenses = client.get("/api/transactions", params={"type": "expense"}).json()
    assert expenses["income_byn"] == "0.00"


def test_search_treats_percent_literally(client: TestClient) -> None:
    client.post("/api/transactions", json=payload(description="Скидка 50%"))
    client.post("/api/transactions", json=payload(description="Скидка 500"))

    found = client.get("/api/transactions", params={"search": "50%"}).json()

    assert found["total"] == 1


def test_pagination(client: TestClient) -> None:
    for day in range(5):
        date = (TODAY - dt.timedelta(days=day)).isoformat()
        client.post("/api/transactions", json=payload(date=date))

    page = client.get("/api/transactions", params={"page": 2, "page_size": 2}).json()

    assert (page["total"], page["pages"], len(page["items"])) == (5, 3, 2)
    assert page["items"][0]["date"] == (TODAY - dt.timedelta(days=2)).isoformat()


def test_invalid_period_is_rejected(client: TestClient) -> None:
    params = {"date_from": TODAY.isoformat(), "date_to": (TODAY - dt.timedelta(1)).isoformat()}

    assert client.get("/api/transactions", params=params).status_code == 422


def test_update_keeps_rate_when_date_and_currency_unchanged(
    client: TestClient, offline_providers: list[FakeRateProvider]
) -> None:
    created = client.post("/api/transactions", json=payload(currency="USD", amount="10")).json()
    go_offline(offline_providers)

    updated = client.put(
        f"/api/transactions/{created['id']}", json=payload(currency="USD", amount="20")
    )

    assert updated.status_code == 200
    assert (updated.json()["rate_source"], updated.json()["amount_byn"]) == ("nbrb", "65.00")


def test_changing_category_marks_it_manual(client: TestClient, seeded_db: Session) -> None:
    created = client.post("/api/transactions", json=payload()).json()
    taxi = category_id(seeded_db, "Транспорт", TransactionType.EXPENSE)

    updated = client.put(f"/api/transactions/{created['id']}", json=payload(category_id=taxi))

    assert updated.json()["category"]["name"] == "Транспорт"
    assert updated.json()["category_source"] == "manual"


def test_get_and_delete(client: TestClient) -> None:
    created = client.post("/api/transactions", json=payload()).json()
    url = f"/api/transactions/{created['id']}"

    assert client.get(url).status_code == 200
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.delete(url).json()["detail"]["code"] == "not_found"


def test_rates_endpoint(client: TestClient) -> None:
    response = client.get("/api/rates/USD", params={"date": TODAY.isoformat()})

    assert response.status_code == 200
    assert response.json()["source_label"] == "НБРБ"


def test_categories_endpoint(client: TestClient, seeded_db: Session) -> None:
    income = client.get("/api/categories", params={"type": "income"}).json()

    assert {item["type"] for item in income} == {"income"}
    assert income[-1]["name"] == "Прочие доходы"  # system fallback goes last
