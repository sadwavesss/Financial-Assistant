"""Business logic for transactions: create, update, delete, list with filters."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.exchange_rates import RateProvider
from app.models import Category, CategorySource, Currency, RateSource, Transaction, TransactionType
from app.schemas.transaction import RateMode, TransactionFilters, TransactionIn
from app.services.errors import InvalidDataError, NotFoundError
from app.services.exchange_rates import (
    RateUnavailableError,
    convert_to_byn,
    find_history_rate,
    get_rate,
)
from app.utils.text import normalize_text


@dataclass(frozen=True)
class TransactionList:
    items: list[Transaction]
    total: int
    page: int
    page_size: int
    income_byn: Decimal
    expense_byn: Decimal

    @property
    def pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))


def get_transaction(db: Session, transaction_id: int) -> Transaction:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise NotFoundError(f"Операция №{transaction_id} не найдена.")
    return transaction


def list_transactions(db: Session, filters: TransactionFilters) -> TransactionList:
    """Filtered page of transactions (newest first) with income/expense totals in BYN."""
    query = _apply_filters(select(Transaction), filters)

    totals = db.execute(
        _apply_filters(
            select(
                func.count(Transaction.id),
                _sum_by_type(TransactionType.INCOME),
                _sum_by_type(TransactionType.EXPENSE),
            ),
            filters,
        )
    ).one()

    items = db.scalars(
        query.options(selectinload(Transaction.category))
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).all()

    return TransactionList(
        items=list(items),
        total=totals[0],
        page=filters.page,
        page_size=filters.page_size,
        income_byn=Decimal(totals[1]).quantize(Decimal("0.01")),
        expense_byn=Decimal(totals[2]).quantize(Decimal("0.01")),
    )


def create_transaction(
    db: Session, data: TransactionIn, providers: Sequence[RateProvider]
) -> Transaction:
    category = _validate_category(db, data.category_id, data.type)
    rate, rate_source = _resolve_rate(db, data, providers)

    transaction = Transaction(
        date=data.date,
        type=data.type,
        amount=data.amount,
        currency=data.currency,
        exchange_rate=rate,
        rate_source=rate_source,
        amount_byn=convert_to_byn(data.amount, rate),
        description=data.description,
        category=category,
        category_source=CategorySource.MANUAL if category else None,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)  # return values exactly as stored (Numeric scale, server defaults)
    return transaction


def update_transaction(
    db: Session, transaction_id: int, data: TransactionIn, providers: Sequence[RateProvider]
) -> Transaction:
    transaction = get_transaction(db, transaction_id)
    category = _validate_category(db, data.category_id, data.type)

    # Keep the stored rate if neither currency nor date changed and no other mode was requested.
    rate_unchanged = (
        data.rate_mode is RateMode.AUTO
        and data.currency is transaction.currency
        and data.date == transaction.date
    )
    if not rate_unchanged:
        transaction.exchange_rate, transaction.rate_source = _resolve_rate(db, data, providers)

    # A category changed by the user is a manual correction (used later to train the classifier).
    if transaction.category_id != data.category_id:
        transaction.category = category
        transaction.category_source = CategorySource.MANUAL if category else None

    transaction.date = data.date
    transaction.type = data.type
    transaction.amount = data.amount
    transaction.currency = data.currency
    transaction.amount_byn = convert_to_byn(data.amount, transaction.exchange_rate)
    transaction.description = data.description
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction_id: int) -> None:
    db.delete(get_transaction(db, transaction_id))
    db.commit()


def _validate_category(
    db: Session, category_id: int | None, transaction_type: TransactionType
) -> Category | None:
    if category_id is None:
        return None
    category = db.get(Category, category_id)
    if category is None:
        raise InvalidDataError("Выбранная категория не существует.", field="category_id")
    if category.type is not transaction_type:
        kind = "доходов" if category.type is TransactionType.INCOME else "расходов"
        raise InvalidDataError(
            f"Категория «{category.name}» предназначена для {kind}.", field="category_id"
        )
    return category


def _resolve_rate(
    db: Session, data: TransactionIn, providers: Sequence[RateProvider]
) -> tuple[Decimal, RateSource | None]:
    if data.currency is Currency.BYN:
        return Decimal(1), None
    if data.rate_mode is RateMode.MANUAL and data.manual_rate is not None:
        return data.manual_rate, RateSource.MANUAL
    if data.rate_mode is RateMode.HISTORY:
        history = find_history_rate(db, data.currency, data.date)
        if history is None:
            raise RateUnavailableError(
                f"В истории нет курса {data.currency.value} близкого к "
                f"{data.date:%d.%m.%Y}. Введите курс вручную.",
                None,
            )
        return history.rate, RateSource.HISTORY
    quote = get_rate(db, data.currency, data.date, providers)
    return quote.rate, quote.source


def _sum_by_type(transaction_type: TransactionType):
    return func.coalesce(
        func.sum(case((Transaction.type == transaction_type, Transaction.amount_byn), else_=0)), 0
    )


def _apply_filters(query: Select, filters: TransactionFilters) -> Select:
    if filters.date_from:
        query = query.where(Transaction.date >= filters.date_from)
    if filters.date_to:
        query = query.where(Transaction.date <= filters.date_to)
    if filters.type:
        query = query.where(Transaction.type == filters.type)
    if filters.category_id:
        query = query.where(Transaction.category_id == filters.category_id)
    if filters.search and (needle := normalize_text(filters.search)):
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Transaction.description_normalized.like(f"%{escaped}%", escape="\\"))
    return query
