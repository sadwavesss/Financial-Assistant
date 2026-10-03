"""Alembic environment: runs migrations against the database configured in app.config."""

from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401  (registers all ORM models in Base.metadata)
from app.config import get_settings
from app.database import Base, build_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
database_url = get_settings().database_url

# SQLite cannot ALTER most column properties; batch mode recreates tables transparently.
common_options = {"target_metadata": target_metadata, "render_as_batch": True}


def run_migrations_offline() -> None:
    """Generate SQL scripts without connecting to the database (`alembic upgrade --sql`)."""
    context.configure(
        url=database_url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **common_options,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations directly to the database."""
    engine = build_engine(database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, **common_options)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
