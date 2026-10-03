"""Migrations must build exactly the schema described by the ORM models."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from app.config import BASE_DIR, get_settings
from app.database import Base, build_engine


@pytest.fixture
def alembic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    """Point migrations at a temporary SQLite file instead of the real database."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}")
    get_settings.cache_clear()
    yield Config(str(BASE_DIR / "alembic.ini"))
    get_settings.cache_clear()


def test_migrations_match_models(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")

    engine = build_engine(get_settings().database_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []


def test_downgrade_removes_all_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    engine = build_engine(get_settings().database_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert tables == {"alembic_version"}
