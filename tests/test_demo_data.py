"""Demo data generator: reproducibility, consistency with categories, compatibility with import."""

import datetime as dt
from pathlib import Path

from app.importers.csv_importer import CsvImporter
from app.models import Currency
from app.services.default_categories import DEFAULT_CATEGORIES
from app.services.demo_data import generate_demo_rows, write_demo_csv

END = dt.date(2026, 11, 3)


def test_same_seed_gives_same_data() -> None:
    assert generate_demo_rows(seed=1, end=END) == generate_demo_rows(seed=1, end=END)
    assert generate_demo_rows(seed=1, end=END) != generate_demo_rows(seed=2, end=END)


def test_rows_cover_period_and_never_go_to_future() -> None:
    rows = generate_demo_rows(months=12, end=END)

    months = {(row.date.year, row.date.month) for row in rows}
    assert len(months) == 12
    assert min(months) == (2025, 12)
    assert max(row.date for row in rows) <= END


def test_labels_are_existing_categories_of_the_right_type() -> None:
    known = {(category.name, category.type) for category in DEFAULT_CATEGORIES}

    assert {(row.category, row.type) for row in generate_demo_rows(end=END)} <= known


def test_contains_foreign_currency_and_income() -> None:
    rows = generate_demo_rows(end=END)

    assert any(row.currency is Currency.USD for row in rows)
    assert sum(row.type.value == "income" for row in rows) >= 24  # salary + advance monthly


def test_csv_is_importable_without_errors(tmp_path: Path) -> None:
    rows = generate_demo_rows(months=3, end=END)
    path = tmp_path / "demo.csv"

    write_demo_csv(rows, path)
    result = CsvImporter().parse(path.read_bytes())

    assert result.errors == []
    assert len(result.rows) == len(rows)
    assert [row.category_name for row in result.rows] == [row.category for row in rows]


def test_csv_without_categories(tmp_path: Path) -> None:
    path = tmp_path / "demo.csv"

    write_demo_csv(generate_demo_rows(months=1, end=END), path, with_categories=False)

    assert "Категория" not in path.read_text(encoding="utf-8-sig").splitlines()[0]
