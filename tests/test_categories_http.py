"""Knowledge base management and categorization over HTTP (API and pages)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import TransactionType
from tests.helpers import category_id


def test_create_update_delete_category(client: TestClient, seeded_db: Session) -> None:
    created = client.post("/api/categories", json={"name": "Питомцы", "type": "expense"})
    assert created.status_code == 201
    category = created.json()

    rule = client.post(f"/api/categories/{category['id']}/rules", json={"keyword": "  ЗооМир "})
    assert rule.json()["keyword"] == "зоомир"

    renamed = client.put(
        f"/api/categories/{category['id']}", json={"name": "Домашние животные", "color": "#123456"}
    )
    assert renamed.json()["name"] == "Домашние животные"

    assert client.delete(f"/api/categories/{category['id']}").status_code == 204


def test_knowledge_base_validation(client: TestClient, seeded_db: Session) -> None:
    groceries = category_id(seeded_db, "Продукты", TransactionType.EXPENSE)
    other = category_id(seeded_db, "Прочие расходы", TransactionType.EXPENSE)

    duplicate_name = client.post("/api/categories", json={"name": "продукты", "type": "expense"})
    duplicate_keyword = client.post(f"/api/categories/{other}/rules", json={"keyword": "Евроопт"})
    short_keyword = client.post(f"/api/categories/{groceries}/rules", json={"keyword": "я"})
    system_delete = client.delete(f"/api/categories/{other}")
    bad_color = client.post(
        "/api/categories", json={"name": "X", "type": "expense", "color": "red"}
    )

    assert duplicate_name.status_code == 422
    assert "Продукты" in duplicate_keyword.json()["detail"]["message"]
    assert short_keyword.status_code == 422
    assert "Системную" in system_delete.json()["detail"]["message"]
    assert bad_color.status_code == 422


def test_new_rule_is_used_immediately(client: TestClient, seeded_db: Session) -> None:
    other = category_id(seeded_db, "Дом и быт", TransactionType.EXPENSE)
    client.post(f"/api/categories/{other}/rules", json={"keyword": "Зоомир"})

    decision = client.post(
        "/api/categorization/predict", json={"description": "ЗООМИР Минск", "type": "expense"}
    ).json()

    assert (decision["category"], decision["source"]) == ("Дом и быт", "rule")
    assert decision["trace"]["steps"][0]["result"][0]["keyword"] == "зоомир"


def test_categorization_status_and_training_errors(client: TestClient, seeded_db: Session) -> None:
    status = client.get("/api/categorization/status").json()
    train = client.post("/api/categorization/train")

    assert status["trained"] is False
    assert train.status_code == 422


def test_pages_render(client: TestClient, seeded_db: Session) -> None:
    categories = client.get("/categories")
    categorization = client.get(
        "/categorization", params={"description": "EVROOPT", "type": "expense"}
    )

    assert "Категории и правила" in categories.text
    assert "евроопт" in categories.text
    assert "База знаний (правила)" in categorization.text
    assert "Продукты" in categorization.text


def test_web_add_rule_and_error(client: TestClient, seeded_db: Session) -> None:
    groceries = category_id(seeded_db, "Продукты", TransactionType.EXPENSE)

    added = client.post(f"/categories/{groceries}/rules", data={"keyword": "Лавка"})
    duplicate = client.post(f"/categories/{groceries}/rules", data={"keyword": "Лавка"})

    assert "Ключевое слово добавлено" in added.text
    assert duplicate.status_code == 422
    assert "уже относится" in duplicate.text


def test_web_train_without_data_shows_error(client: TestClient, seeded_db: Session) -> None:
    response = client.post("/categorization/train")

    assert "Недостаточно размеченных операций" in response.text
