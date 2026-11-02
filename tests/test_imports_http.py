"""Import over HTTP: REST API and the upload -> preview -> confirm pages."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.importers.csv_importer import TEMPLATE
from app.models import Transaction
from app.web import upload_store

GOOD_FILE = ("ops.csv", "Дата;Сумма;Описание\n01.10.2026;-10;Кофе\n02.10.2026;-5;Такси\n".encode())


@pytest.fixture(autouse=True)
def temporary_upload_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload_store, "STORE_DIR", tmp_path)


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Transaction))


def test_template_download(client: TestClient) -> None:
    response = client.get("/api/imports/template.csv")

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.decode("utf-8-sig") == TEMPLATE


def test_api_preview_and_import(client: TestClient, db: Session) -> None:
    preview = client.post("/api/imports/preview", files={"file": GOOD_FILE}).json()
    assert (preview["new"], preview["duplicates"], preview["errors"]) == (2, 0, 0)
    assert count(db) == 0

    report = client.post("/api/imports", files={"file": GOOD_FILE}).json()
    assert report == {"created": 2, "duplicates": 0, "errors": []}
    assert count(db) == 2


def test_api_rejects_unknown_format_and_bad_file(client: TestClient) -> None:
    unknown = client.post("/api/imports/preview?format=xlsx", files={"file": GOOD_FILE})
    broken = client.post("/api/imports/preview", files={"file": ("x.csv", b"foo;bar\n1;2\n")})

    assert unknown.status_code == broken.status_code == 422
    assert broken.json()["detail"]["code"] == "import_file_error"


def test_web_upload_preview_confirm(client: TestClient, db: Session, tmp_path: Path) -> None:
    preview = client.post("/import", files={"file": GOOD_FILE}, data={"format": "csv"})
    assert preview.status_code == 200
    assert "Импортировать 2 операций" in preview.text
    token = re.search(r"/import/([0-9a-f]{32})/confirm", preview.text).group(1)
    assert count(db) == 0

    result = client.post(f"/import/{token}/confirm")
    assert "Добавлено операций: <strong>2</strong>" in result.text
    assert count(db) == 2
    assert list(tmp_path.iterdir()) == []  # the temporary file is removed

    repeated = client.post(f"/import/{token}/confirm")
    assert repeated.status_code == 404


def test_web_cancel_removes_file(client: TestClient, tmp_path: Path) -> None:
    preview = client.post("/import", files={"file": GOOD_FILE})
    token = re.search(r"/import/([0-9a-f]{32})/confirm", preview.text).group(1)

    response = client.post(f"/import/{token}/cancel")

    assert response.url.path == "/import"
    assert list(tmp_path.iterdir()) == []


def test_web_shows_file_error(client: TestClient) -> None:
    response = client.post("/import", files={"file": ("x.csv", b"")})

    assert response.status_code == 422
    assert "Файл пуст" in response.text


def test_web_rejects_foreign_tokens(client: TestClient) -> None:
    assert client.post("/import/..%2F..%2Fetc/confirm").status_code == 404
    assert client.post(f"/import/{'0' * 32}/confirm").status_code == 404
