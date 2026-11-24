"""End-to-end scenarios through the web interface, from an empty database to recommendations.

Each scenario goes through all components the way a user does: import -> categorization
(rules + ML) -> analytics -> recurring payments -> forecast -> rule inference.
"""

import datetime as dt
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CategorySource, Transaction, TransactionType
from app.services.categorization import training_data
from app.services.demo_data import generate_demo_rows, write_demo_csv
from app.web import upload_store
from tests.helpers import category_id

PAGES = [
    "/", "/transactions", "/transactions/new", "/transactions?needs_review=true", "/import",
    "/analytics", "/analytics?period=12m&granularity=month", "/recurring", "/forecast",
    "/forecast?granularity=week&horizon=8", "/recommendations", "/categories", "/categorization",
    "/categorization?description=EVROOPT&type=expense", "/docs",
]  # fmt: skip


@pytest.fixture(autouse=True)
def temporary_upload_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_store, "STORE_DIR", tmp_path / "uploads")


def upload(client: TestClient, path: Path) -> str:
    """Upload a file on the import page and confirm it; returns the result page text."""
    preview = client.post("/import", files={"file": (path.name, path.read_bytes())})
    token = re.search(r"/import/([0-9a-f]{32})/confirm", preview.text).group(1)
    return client.post(f"/import/{token}/confirm").text


def test_full_user_journey(client: TestClient, seeded_db: Session, tmp_path: Path) -> None:
    today = dt.date.today()
    labeled, unlabeled = tmp_path / "labeled.csv", tmp_path / "new.csv"
    rows = generate_demo_rows(months=12, end=today)
    history = [r for r in rows if r.date < today - dt.timedelta(days=30)]
    recent = [r for r in rows if r.date >= today - dt.timedelta(days=30)]
    write_demo_csv(history, labeled)  # categories given -> manual labels for training
    write_demo_csv(recent, unlabeled, with_categories=False)  # to be categorized automatically

    # 1. Import labeled history and train the classifier from the web page.
    assert f"Добавлено операций: <strong>{len(history)}</strong>" in upload(client, labeled)
    trained = client.post("/categorization/train")
    assert "Модель обучена" in trained.text

    # 2. Import the last month without categories: the hybrid categorizer assigns them.
    assert f"Добавлено операций: <strong>{len(recent)}</strong>" in upload(client, unlabeled)
    automatic = seeded_db.scalars(
        select(Transaction).where(Transaction.category_source != CategorySource.MANUAL)
    ).all()
    assert len(automatic) == len(recent)
    assert all(t.categorization_trace for t in automatic)
    assert (
        sum(t.category_source is not CategorySource.FALLBACK for t in automatic) / len(automatic)
        > 0.9
    )  # almost everything is recognized by rules or the model

    # 3. Re-importing the same file: every row is a duplicate, nothing to confirm.
    again = client.post("/import", files={"file": (unlabeled.name, unlabeled.read_bytes())})
    assert "В файле нет новых операций" in again.text
    assert "/confirm" not in again.text

    # 4. Every page works on the full data set.
    for page in PAGES:
        assert client.get(page).status_code == 200, page

    # 5. The analysis chain produces consistent results.
    analytics = client.get("/api/analytics", params={"period": "12m"}).json()
    recurring = client.get("/api/recurring").json()
    forecast = client.get("/api/forecast").json()
    recommendations = client.get("/api/recommendations").json()
    evaluation = client.post("/api/categorization/evaluate").json()

    total = seeded_db.scalar(select(func.count()).select_from(Transaction))
    assert analytics["summary"]["count"] <= total
    assert {p["name"] for p in recurring["payments"]} >= {"Яндекс Плюс", "МТС, мобильная связь"}
    assert len(forecast["forecast"]) == 3 and sum(m["selected"] for m in forecast["models"]) == 1
    assert recommendations["recommendations"], "rules fire on a realistic budget"
    hybrid = {v["variant"]: v for v in evaluation["scenarios"][0]["variants"]}
    assert hybrid["hybrid"]["accuracy"] >= hybrid["rules"]["accuracy"]


def test_manual_correction_becomes_training_data(client: TestClient, seeded_db: Session) -> None:
    form = {
        "date": dt.date.today().isoformat(),
        "type": "expense",
        "amount": "15",
        "currency": "BYN",
    }
    description = "Лавка «Хлебный дом»"

    # Unknown merchant, no model: fallback category, marked for review.
    client.post("/transactions/new", data={**form, "description": description})
    created = seeded_db.scalars(select(Transaction)).one()
    assert created.category_source is CategorySource.FALLBACK and created.needs_review
    assert description in client.get("/transactions?needs_review=true").text

    # The user picks the right category: it becomes a manual label and the review flag goes.
    groceries = category_id(seeded_db, "Продукты", TransactionType.EXPENSE)
    client.post(
        f"/transactions/{created.id}/edit",
        data={**form, "description": description, "category_id": str(groceries)},
    )
    seeded_db.expire_all()
    assert (created.category_source, created.needs_review) == (CategorySource.MANUAL, False)
    texts, labels = training_data(seeded_db)
    assert (texts, labels) == ([description], [groceries])
