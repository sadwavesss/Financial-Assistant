"""Smoke tests for the application skeleton."""

from fastapi.testclient import TestClient

from app import __version__
from app.config import BASE_DIR, Settings


def test_health_reports_ok(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_index_page_renders(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "Финансовый ассистент" in response.text


def test_relative_sqlite_path_is_resolved_against_project_root() -> None:
    settings = Settings(database_url="sqlite:///data/test.db")

    assert settings.database_url == f"sqlite:///{(BASE_DIR / 'data' / 'test.db').as_posix()}"


def test_non_sqlite_url_is_left_unchanged() -> None:
    url = "postgresql+psycopg://user:secret@localhost:5432/finance"

    assert Settings(database_url=url).database_url == url
