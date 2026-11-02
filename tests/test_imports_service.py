"""Import service: preview statuses, duplicates, categories, exchange rates, limits."""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.importers import ImportFileError
from app.importers.csv_importer import CsvImporter
from app.models import CategorySource, Currency, RateSource, Transaction
from app.services.imports import RowStatus, preview_import, run_import
from tests.helpers import FakeRateProvider

importer = CsvImporter()
HEADER = "Дата;Тип;Сумма;Валюта;Описание;Категория\n"


def csv(*lines: str) -> bytes:
    return (HEADER + "\n".join(lines) + "\n").encode()


def saved(db: Session) -> list[Transaction]:
    return list(db.scalars(select(Transaction).order_by(Transaction.id)))


def test_preview_saves_nothing(seeded_db: Session) -> None:
    preview = preview_import(seeded_db, csv("01.10.2026;расход;10;BYN;Кофе;"), importer)

    assert preview.count(RowStatus.NEW) == 1
    assert saved(seeded_db) == []


def test_import_then_reimport_skips_duplicates(
    seeded_db: Session, providers: list[FakeRateProvider]
) -> None:
    content = csv("01.10.2026;расход;10;BYN;Кофе;", "02.10.2026;доход;100;BYN;Зарплата;")

    first = run_import(seeded_db, content, importer, providers)
    second = run_import(seeded_db, content, importer, providers)

    assert (first.created, first.duplicates) == (2, 0)
    assert (second.created, second.duplicates) == (0, 2)
    assert len(saved(seeded_db)) == 2


def test_identical_rows_in_one_file_are_both_imported(
    seeded_db: Session, providers: list[FakeRateProvider]
) -> None:
    row = "01.10.2026;расход;3,50;BYN;Кофе;"

    report = run_import(seeded_db, csv(row, row), importer, providers)

    assert report.created == 2


def test_overlapping_file_imports_only_new_rows(
    seeded_db: Session, providers: list[FakeRateProvider]
) -> None:
    run_import(seeded_db, csv("01.10.2026;расход;10;BYN;Кофе;"), importer, providers)

    report = run_import(
        seeded_db,
        csv("01.10.2026;расход;10;BYN;Кофе;", "03.10.2026;расход;7;BYN;Такси;"),
        importer,
        providers,
    )

    assert (report.created, report.duplicates) == (1, 1)


def test_category_from_file_is_matched_by_name(
    seeded_db: Session, providers: list[FakeRateProvider]
) -> None:
    content = csv(
        "01.10.2026;расход;10;BYN;Евроопт;продукты", "01.10.2026;расход;5;BYN;X;Нет такой"
    )

    preview = preview_import(seeded_db, content, importer)
    run_import(seeded_db, content, importer, providers)

    assert "не найдена" in preview.rows[1].message
    groceries, unknown = saved(seeded_db)
    assert (groceries.category.name, groceries.category_source) == (
        "Продукты",
        CategorySource.MANUAL,
    )
    assert (unknown.category, unknown.category_source) == (None, None)


def test_category_of_wrong_type_is_not_assigned(seeded_db: Session) -> None:
    preview = preview_import(seeded_db, csv("01.10.2026;расход;10;BYN;Аванс;Зарплата"), importer)

    assert preview.rows[0].category is None


def test_usd_rows_get_online_rate(seeded_db: Session, providers: list[FakeRateProvider]) -> None:
    run_import(seeded_db, csv("01.10.2026;расход;10;USD;Steam;"), importer, providers)

    (transaction,) = saved(seeded_db)
    assert (transaction.rate_source, transaction.amount_byn) == (RateSource.NBRB, Decimal("32.50"))


def test_offline_usd_rows_use_history_or_become_errors(
    seeded_db: Session, offline_providers: list[FakeRateProvider]
) -> None:
    seeded_db.add(
        Transaction(
            date=dt.date(2026, 10, 1),
            type="expense",
            amount=Decimal(1),
            currency=Currency.USD,
            exchange_rate=Decimal("3.1"),
            rate_source=RateSource.NBRB,
            amount_byn=Decimal("3.1"),
        )
    )
    seeded_db.commit()
    content = csv("03.10.2026;расход;10;USD;Steam;", "01.06.2026;расход;10;USD;Steam;")

    report = run_import(seeded_db, content, importer, offline_providers)

    assert report.created == 1
    assert [error.line for error in report.errors] == [3]
    imported = saved(seeded_db)[-1]
    assert (imported.rate_source, imported.amount_byn) == (RateSource.HISTORY, Decimal("31.00"))


def test_row_errors_are_reported_and_valid_rows_saved(
    seeded_db: Session, providers: list[FakeRateProvider]
) -> None:
    report = run_import(
        seeded_db,
        csv("01.10.2026;расход;10;BYN;Кофе;", "xx;расход;10;BYN;Кофе;"),
        importer,
        providers,
    )

    assert report.created == 1
    assert report.errors[0].line == 3


def test_file_size_limit(seeded_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "import_max_bytes", 10)

    with pytest.raises(ImportFileError, match="МБ"):
        preview_import(seeded_db, csv("01.10.2026;расход;10;BYN;Кофе;"), importer)


def test_row_count_limit(seeded_db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "import_max_rows", 1)

    with pytest.raises(ImportFileError, match="строк"):
        preview_import(
            seeded_db, csv("01.10.2026;расход;1;BYN;A;", "01.10.2026;расход;2;BYN;B;"), importer
        )
