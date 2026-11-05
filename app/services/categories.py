"""Business logic for categories and keyword rules (the knowledge base of categorization)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Category, CategoryRule, Transaction, TransactionType
from app.schemas.category import CategoryIn, CategoryUpdate
from app.services.default_categories import DEFAULT_CATEGORIES
from app.services.errors import InvalidDataError, NotFoundError
from app.utils.text import normalize_text

MIN_KEYWORD_LENGTH = 2


def list_categories(db: Session, transaction_type: TransactionType | None = None) -> list[Category]:
    """Categories sorted by type and name; system fallbacks ("Прочие ...") go last."""
    query = (
        select(Category)
        .options(selectinload(Category.rules))
        .order_by(Category.type, Category.is_system, Category.name)
    )
    if transaction_type:
        query = query.where(Category.type == transaction_type)
    return list(db.scalars(query))


def transaction_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Transaction.category_id, func.count()).group_by(Transaction.category_id)
    ).all()
    return {category_id: count for category_id, count in rows if category_id is not None}


def get_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None:
        raise NotFoundError(f"Категория №{category_id} не найдена.")
    return category


def create_category(db: Session, data: CategoryIn) -> Category:
    _ensure_unique_name(db, data.name, data.type)
    category = Category(name=data.name, type=data.type, color=data.color)
    db.add(category)
    db.commit()
    return category


def update_category(db: Session, category_id: int, data: CategoryUpdate) -> Category:
    category = get_category(db, category_id)
    if normalize_text(data.name) != normalize_text(category.name):
        _ensure_unique_name(db, data.name, category.type)
    category.name, category.color = data.name, data.color
    db.commit()
    return category


def delete_category(db: Session, category_id: int) -> None:
    """Delete a category with its rules; its transactions stay and become uncategorized."""
    category = get_category(db, category_id)
    if category.is_system:
        raise InvalidDataError(
            f"Системную категорию «{category.name}» удалить нельзя: "
            "она используется, когда категорию определить не удалось."
        )
    db.delete(category)
    db.commit()


def add_rule(db: Session, category_id: int, keyword: str) -> CategoryRule:
    category = get_category(db, category_id)
    normalized = normalize_text(keyword)
    if len(normalized) < MIN_KEYWORD_LENGTH:
        raise InvalidDataError(
            f"Ключевое слово должно содержать не менее {MIN_KEYWORD_LENGTH} символов.",
            field="keyword",
        )
    existing = db.scalar(select(CategoryRule).where(CategoryRule.keyword == normalized))
    if existing:
        raise InvalidDataError(
            f"Ключевое слово «{normalized}» уже относится к категории «{existing.category.name}».",
            field="keyword",
        )
    rule = CategoryRule(category=category, keyword=normalized)
    db.add(rule)
    db.commit()
    return rule


def delete_rule(db: Session, rule_id: int) -> None:
    rule = db.get(CategoryRule, rule_id)
    if rule is None:
        raise NotFoundError(f"Правило №{rule_id} не найдено.")
    db.delete(rule)
    db.commit()


def seed_default_categories(db: Session) -> int:
    """Create the initial categories and rules if there are no categories yet.

    Runs only on an empty table, so categories the user deleted or renamed are never restored.
    Returns the number of created categories.
    """
    if db.scalar(select(func.count()).select_from(Category)):
        return 0

    for default in DEFAULT_CATEGORIES:
        keywords = dict.fromkeys(normalize_text(word) for word in default.keywords)
        db.add(
            Category(
                name=default.name,
                type=default.type,
                color=default.color,
                is_system=default.is_system,
                rules=[CategoryRule(keyword=keyword) for keyword in keywords],
            )
        )
    db.commit()
    return len(DEFAULT_CATEGORIES)


def _ensure_unique_name(db: Session, name: str, transaction_type: TransactionType) -> None:
    same_type = db.scalars(select(Category.name).where(Category.type == transaction_type))
    if any(normalize_text(existing) == normalize_text(name) for existing in same_type):
        raise InvalidDataError(f"Категория «{name}» уже существует.", field="name")
