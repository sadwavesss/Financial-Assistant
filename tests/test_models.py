"""Database schema rules: constraints, cascades and enum storage."""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Category, CategoryRule, Currency, Transaction, TransactionType


def make_category(db: Session, name: str = "Продукты") -> Category:
    category = Category(
        name=name, type=TransactionType.EXPENSE, rules=[CategoryRule(keyword="евроопт")]
    )
    db.add(category)
    db.commit()
    return category


def make_transaction(category: Category | None = None, amount: str = "12.50") -> Transaction:
    transaction = Transaction(
        date=dt.date(2026, 9, 1),
        type=TransactionType.EXPENSE,
        amount=Decimal(amount),
        amount_byn=Decimal(amount),
        description="Евроопт",
    )
    # Assigning the relationship only when given: `category=None` would overwrite category_id.
    if category is not None:
        transaction.category = category
    return transaction


def test_transaction_defaults_and_decimal_precision(db: Session) -> None:
    db.add(make_transaction(amount="1234567.89"))
    db.commit()

    saved = db.scalars(select(Transaction)).one()
    assert saved.currency is Currency.BYN
    assert saved.exchange_rate == Decimal(1)
    assert saved.amount == Decimal("1234567.89")
    assert saved.created_at is not None


def test_enums_are_stored_as_readable_values(db: Session) -> None:
    db.add(make_transaction())
    db.commit()

    raw = db.execute(text("SELECT type, currency FROM transactions")).one()
    assert tuple(raw) == ("expense", "BYN")


@pytest.mark.parametrize("amount", ["0", "-5.00"])
def test_non_positive_amount_is_rejected(db: Session, amount: str) -> None:
    db.add(make_transaction(amount=amount))

    with pytest.raises(IntegrityError):
        db.commit()


def test_category_name_is_unique_per_type(db: Session) -> None:
    make_category(db)
    db.add(Category(name="Продукты", type=TransactionType.EXPENSE))

    with pytest.raises(IntegrityError):
        db.commit()


def test_same_name_allowed_for_income_and_expense(db: Session) -> None:
    db.add_all(
        [
            Category(name="Прочее", type=TransactionType.EXPENSE),
            Category(name="Прочее", type=TransactionType.INCOME),
        ]
    )
    db.commit()

    assert len(db.scalars(select(Category)).all()) == 2


def test_deleting_category_keeps_transactions_and_removes_rules(db: Session) -> None:
    category = make_category(db)
    db.add(make_transaction(category))
    db.commit()

    db.delete(category)
    db.commit()
    db.expire_all()

    transaction = db.scalars(select(Transaction)).one()
    assert transaction.category_id is None
    assert db.scalars(select(CategoryRule)).all() == []


def test_foreign_keys_are_enforced(db: Session) -> None:
    transaction = make_transaction()
    transaction.category_id = 999
    db.add(transaction)

    with pytest.raises(IntegrityError):
        db.commit()
