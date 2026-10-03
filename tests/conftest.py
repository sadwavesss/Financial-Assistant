"""Shared test fixtures: an isolated in-memory database and an HTTP test client."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers all ORM models in Base.metadata)
from app.database import Base, build_engine, get_db
from app.main import app


@pytest.fixture
def engine() -> Iterator[Engine]:
    # StaticPool keeps a single connection, so the in-memory database lives for the whole test.
    test_engine = build_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
