"""HTML pages of transactions: forms, Russian validation messages, redirects."""

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import get_rate_providers
from app.main import app
from app.models import Transaction
from tests.helpers import FakeRateProvider

TODAY = dt.date.today().isoformat()


def form(**overrides: str) -> dict[str, str]:
    return {"date": TODAY, "type": "expense", "amount": "12,50", "currency": "BYN", **overrides}


def test_empty_list_page(client: TestClient) -> None:
    response = client.get("/transactions")

    assert response.status_code == 200
    assert "Операций не найдено" in response.text


def test_new_form_page(client: TestClient, seeded_db: Session) -> None:
    response = client.get("/transactions/new")

    assert response.status_code == 200
    assert "Новая операция" in response.text
    assert "Продукты" in response.text


def test_create_with_comma_decimal_redirects_to_list(client: TestClient, db: Session) -> None:
    response = client.post("/transactions/new", data=form(description="Кофе"))

    assert response.status_code == 200  # TestClient follows the 303 redirect
    assert response.url.path == "/transactions"
    assert "Операция добавлена" in response.text
    assert db.scalars(select(Transaction)).one().amount_byn == 12.5


def test_validation_errors_are_shown_in_russian(client: TestClient) -> None:
    response = client.post("/transactions/new", data=form(amount="0"))

    assert response.status_code == 422
    assert "Значение должно быть больше нуля" in response.text


def test_rate_unavailable_offers_history_then_saves(
    client: TestClient, db: Session, offline_providers: list[FakeRateProvider]
) -> None:
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    client.post("/transactions/new", data=form(date=yesterday, currency="USD", amount="5"))
    app.dependency_overrides[get_rate_providers] = lambda: offline_providers

    failed = client.post("/transactions/new", data=form(currency="USD", amount="10"))
    assert failed.status_code == 422
    assert "Курс из истории операций" in failed.text
    assert "3,25 BYN" in failed.text

    saved = client.post(
        "/transactions/new", data=form(currency="USD", amount="10", rate_mode="history")
    )
    assert saved.url.path == "/transactions"
    assert len(db.scalars(select(Transaction)).all()) == 2


def test_edit_and_delete(client: TestClient, db: Session) -> None:
    client.post("/transactions/new", data=form(description="Старое"))
    transaction_id = db.scalars(select(Transaction.id)).one()

    edit_page = client.get(f"/transactions/{transaction_id}/edit")
    assert "Старое" in edit_page.text

    saved = client.post(f"/transactions/{transaction_id}/edit", data=form(description="Новое"))
    assert "Операция сохранена" in saved.text
    assert "Новое" in saved.text

    deleted = client.post(f"/transactions/{transaction_id}/delete")
    assert "Операция удалена" in deleted.text
    assert db.scalars(select(Transaction)).all() == []


def test_missing_transaction_shows_html_error(client: TestClient) -> None:
    response = client.get("/transactions/999/edit")

    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "не найдена" in response.text


def test_invalid_filter_shows_message(client: TestClient) -> None:
    response = client.get(
        "/transactions", params={"date_from": "2026-09-10", "date_to": "2026-09-01"}
    )

    assert response.status_code == 200
    assert "Начало периода позже его конца" in response.text
