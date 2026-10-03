"""Business logic for categories and keyword rules."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, CategoryRule
from app.services.default_categories import DEFAULT_CATEGORIES
from app.utils.text import normalize_text


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
