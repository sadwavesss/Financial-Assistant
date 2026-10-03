"""Default categories: data consistency and idempotent seeding."""

import re
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryRule, TransactionType
from app.services.categories import seed_default_categories
from app.services.default_categories import DEFAULT_CATEGORIES
from app.utils.text import normalize_text


def test_keywords_are_unique_across_categories() -> None:
    keywords = Counter(
        normalize_text(word) for category in DEFAULT_CATEGORIES for word in category.keywords
    )
    duplicates = [word for word, count in keywords.items() if count > 1]

    assert duplicates == []


def test_category_names_are_unique_per_type() -> None:
    names = Counter((category.name, category.type) for category in DEFAULT_CATEGORIES)

    assert all(count == 1 for count in names.values())


def test_colors_are_hex() -> None:
    assert all(re.fullmatch(r"#[0-9a-f]{6}", category.color) for category in DEFAULT_CATEGORIES)


def test_each_type_has_one_system_fallback_without_keywords() -> None:
    for transaction_type in TransactionType:
        system = [c for c in DEFAULT_CATEGORIES if c.type is transaction_type and c.is_system]
        assert len(system) == 1
        assert system[0].keywords == ()


def test_seed_creates_categories_with_normalized_rules(db: Session) -> None:
    created = seed_default_categories(db)

    assert created == len(DEFAULT_CATEGORIES)
    assert db.scalar(select(func.count()).select_from(Category)) == len(DEFAULT_CATEGORIES)
    rublevski = db.scalars(select(CategoryRule).where(CategoryRule.keyword == "рублевский")).one()
    assert rublevski.category.name == "Продукты"


def test_seed_does_nothing_when_categories_exist(db: Session) -> None:
    db.add(Category(name="Своя категория", type=TransactionType.EXPENSE))
    db.commit()

    assert seed_default_categories(db) == 0
    assert db.scalar(select(func.count()).select_from(Category)) == 1


def test_normalize_text() -> None:
    assert normalize_text("  Рублёвский   N1 ") == "рублевский n1"
