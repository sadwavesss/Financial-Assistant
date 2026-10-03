"""Migrations must build exactly the schema described by the ORM models."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

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


def test_rate_source_migration_keeps_existing_data(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "eaacdd426377")
    engine = build_engine(get_settings().database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO transactions (date, type, amount, currency, exchange_rate, "
                "amount_byn, description) "
                "VALUES ('2026-09-01', 'expense', 10, 'USD', 3.02, 30.2, 'Оплата  STEAM')"
            )
        )

    command.upgrade(alembic_config, "head")

    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT description_normalized, rate_source FROM transactions")
        ).one()
        # New rate sources are accepted by the updated CHECK constraint.
        connection.execute(
            text(
                "INSERT INTO exchange_rates (currency, date, rate, source) "
                "VALUES ('USD', '2026-09-01', 3.02, 'cbr')"
            )
        )
    engine.dispose()

    assert tuple(row) == ("оплата steam", "nbrb")


def test_downgrade_removes_all_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")

    engine = build_engine(get_settings().database_url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()

    assert tables == {"alembic_version"}
