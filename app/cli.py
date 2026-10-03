"""Command-line utilities: `python -m app.cli <command>`."""

import argparse

from alembic import command
from alembic.config import Config

from app.config import BASE_DIR
from app.database import SessionLocal
from app.services.categories import seed_default_categories


def init_db() -> None:
    """Apply all migrations and create the default categories on an empty database."""
    command.upgrade(Config(str(BASE_DIR / "alembic.ini")), "head")
    with SessionLocal() as db:
        created = seed_default_categories(db)
    if created:
        print(f"База данных готова. Создано стартовых категорий: {created}.")
    else:
        print("База данных готова. Категории уже существуют, стартовый набор не добавлялся.")


COMMANDS = {
    "init-db": (init_db, "применить миграции и создать стартовые категории"),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Финансовый ассистент")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        subparsers.add_parser(name, help=help_text)

    args = parser.parse_args(argv)
    handler, _ = COMMANDS[args.command]
    handler()


if __name__ == "__main__":
    main()
