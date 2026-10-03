"""Shared test fixtures: an isolated in-memory database, fake rate sources and an HTTP client."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers all ORM models in Base.metadata)
from app.database import Base, build_engine, get_db
from app.dependencies import get_rate_providers
from app.main import app
from app.models import RateSource
from app.services.categories import seed_default_categories
from tests.helpers import ONLINE_SOURCES, FakeRateProvider


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
def seeded_db(db: Session) -> Session:
    seed_default_categories(db)
    return db


@pytest.fixture
def providers() -> list[FakeRateProvider]:
    """All sources online; each answers differently, so a wrong order would be noticed."""
    return [
        FakeRateProvider(RateSource.NBRB, "3.25"),
        FakeRateProvider(RateSource.CBR, "3.26"),
        FakeRateProvider(RateSource.CURRENCY_API, "3.27"),
    ]


@pytest.fixture
def offline_providers() -> list[FakeRateProvider]:
    """No Internet: every online source fails."""
    return [FakeRateProvider(source, None) for source in ONLINE_SOURCES]


@pytest.fixture
def client(db: Session, providers: list[FakeRateProvider]) -> Iterator[TestClient]:
    """HTTP client with the test database and offline fake rate sources."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_rate_providers] = lambda: providers
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
