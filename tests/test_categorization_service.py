"""Hybrid categorization with the database: creation, editing, import, training, evaluation."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.csv_importer import CsvImporter
from app.models import CategorySource, Transaction, TransactionType
from app.schemas.transaction import TransactionIn
from app.services import categorization
from app.services.categorization_eval import evaluate, load_last_report
from app.services.demo_data import generate_demo_rows, write_demo_csv
from app.services.errors import InvalidDataError
from app.services.imports import run_import
from app.services.transactions import create_transaction, update_transaction
from tests.helpers import FakeRateProvider, category_id

EXPENSE = TransactionType.EXPENSE
DAY = dt.date(2026, 10, 1)


def new(description: str, category: int | None = None) -> TransactionIn:
    return TransactionIn(
        date=DAY, type=EXPENSE, amount=Decimal(10), description=description, category_id=category
    )


def load_demo(db: Session, providers: list[FakeRateProvider], tmp_path: Path, months: int = 6):
    """Labeled demo data imported with its categories (they become manual labels)."""
    path = tmp_path / "demo.csv"
    write_demo_csv(generate_demo_rows(months=months, end=dt.date(2026, 10, 31)), path)
    run_import(db, path.read_bytes(), CsvImporter(), providers)


def test_new_transaction_is_categorized_by_rule(seeded_db: Session, providers) -> None:
    transaction = create_transaction(seeded_db, new("EVROOPT MINSK"), providers)

    assert transaction.category.name == "Продукты"
    assert transaction.category_source is CategorySource.RULE
    assert transaction.categorization_trace["steps"][0]["result"][0]["keyword"] == "evroopt"


def test_unknown_description_without_model_goes_to_fallback(seeded_db: Session, providers) -> None:
    transaction = create_transaction(seeded_db, new("ИП Петров"), providers)

    assert transaction.category.name == "Прочие расходы"
    assert (transaction.category_source, transaction.needs_review) == (
        CategorySource.FALLBACK,
        True,
    )


def test_user_correction_becomes_manual(seeded_db: Session, providers) -> None:
    transaction = create_transaction(seeded_db, new("ИП Петров"), providers)
    groceries = category_id(seeded_db, "Продукты", EXPENSE)

    updated = update_transaction(seeded_db, transaction.id, new("ИП Петров", groceries), providers)

    assert updated.category_source is CategorySource.MANUAL
    assert (updated.needs_review, updated.categorization_trace) == (False, None)


def test_changed_description_recategorizes_automatic_category(
    seeded_db: Session, providers
) -> None:
    transaction = create_transaction(seeded_db, new("Евроопт"), providers)

    updated = update_transaction(seeded_db, transaction.id, new("Такси"), providers)

    assert updated.category.name == "Транспорт"


def test_recategorize_never_touches_manual_categories(seeded_db: Session, providers) -> None:
    cafe = category_id(seeded_db, "Кафе и рестораны", EXPENSE)
    manual = create_transaction(seeded_db, new("Евроопт", cafe), providers)  # deliberately "wrong"
    automatic = create_transaction(seeded_db, new("Евроопт"), providers)

    report = categorization.recategorize_all(seeded_db)

    assert report.processed == 1
    assert (manual.category_id, manual.category_source) == (cafe, CategorySource.MANUAL)
    assert automatic.category_source is CategorySource.RULE


def test_training_data_excludes_model_guesses_and_disputed_rules(
    seeded_db: Session, providers
) -> None:
    groceries = category_id(seeded_db, "Продукты", EXPENSE)
    create_transaction(seeded_db, new("Магазин у дома", groceries), providers)  # manual
    create_transaction(seeded_db, new("Евроопт"), providers)  # rule
    disputed = create_transaction(seeded_db, new("Гиппо"), providers)
    disputed.needs_review = True
    guessed = create_transaction(seeded_db, new("Гиппо"), providers)
    guessed.category_source = CategorySource.ML
    seeded_db.commit()

    texts, _ = categorization.training_data(seeded_db)

    assert sorted(texts) == ["Евроопт", "Магазин у дома"]


def test_training_needs_enough_labels(seeded_db: Session) -> None:
    with pytest.raises(InvalidDataError, match="Недостаточно"):
        categorization.train_classifier(seeded_db)


def test_trained_model_categorizes_descriptions_without_keywords(
    seeded_db: Session, providers, tmp_path: Path, isolated_models_dir: Path
) -> None:
    load_demo(seeded_db, providers, tmp_path)

    classifier = categorization.train_classifier(seeded_db)
    transaction = create_transaction(seeded_db, new("ИП Петров, магазин у дома"), providers)

    assert (isolated_models_dir / "categorizer.joblib").is_file()
    assert classifier.info.samples > 100
    assert transaction.category.name == "Продукты"
    assert transaction.category_source is CategorySource.ML
    assert transaction.category_confidence >= 0.6


def test_import_without_categories_uses_the_hybrid(seeded_db: Session, providers) -> None:
    content = "Дата;Сумма;Описание\n01.10.2026;-5;Wildberries\n01.10.2026;-5;Неизвестно\n".encode()

    run_import(seeded_db, content, CsvImporter(), providers)

    rows = seeded_db.scalars(select(Transaction).order_by(Transaction.id)).all()
    assert [(t.category.name, t.category_source) for t in rows] == [
        ("Маркетплейсы", CategorySource.RULE),
        ("Прочие расходы", CategorySource.FALLBACK),
    ]


def test_evaluation_compares_three_variants(seeded_db: Session, providers, tmp_path: Path) -> None:
    load_demo(seeded_db, providers, tmp_path)

    report = evaluate(seeded_db)

    assert [s.scenario for s in report.scenarios] == ["random", "new_descriptions"]
    for scenario in report.scenarios:
        assert [v.variant for v in scenario.variants] == ["rules", "ml", "hybrid"]
        metrics = {v.variant: v for v in scenario.variants}
        # The hybrid is never worse than its best single component on these data.
        assert (
            metrics["hybrid"].accuracy
            >= max(metrics["rules"].accuracy, metrics["ml"].accuracy) - 0.01
        )
    assert load_last_report()["samples"] == report.samples


def test_evaluation_needs_manual_labels(seeded_db: Session) -> None:
    with pytest.raises(InvalidDataError):
        evaluate(seeded_db)
