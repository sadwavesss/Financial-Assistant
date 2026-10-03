"""Rate resolution order: cache -> online sources -> local history."""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Currency, ExchangeRate, RateSource, Transaction, TransactionType
from app.services.exchange_rates import (
    RateUnavailableError,
    convert_to_byn,
    find_history_rate,
    get_rate,
)
from tests.helpers import FakeRateProvider

DAY = dt.date(2026, 9, 15)


def add_usd_operation(db: Session, on_date: dt.date, rate: str) -> None:
    db.add(
        Transaction(
            date=on_date,
            type=TransactionType.EXPENSE,
            amount=Decimal("10"),
            currency=Currency.USD,
            exchange_rate=Decimal(rate),
            rate_source=RateSource.NBRB,
            amount_byn=Decimal(rate) * 10,
        )
    )
    db.commit()


def test_first_available_source_is_used_and_cached(
    db: Session, providers: list[FakeRateProvider]
) -> None:
    quote = get_rate(db, Currency.USD, DAY, providers)

    assert (quote.rate, quote.source) == (Decimal("3.25"), RateSource.NBRB)
    cached = db.scalars(select(ExchangeRate)).one()
    assert (cached.date, cached.rate, cached.source) == (DAY, Decimal("3.25"), RateSource.NBRB)


def test_cached_rate_is_used_without_network(
    db: Session, providers: list[FakeRateProvider]
) -> None:
    get_rate(db, Currency.USD, DAY, providers)
    get_rate(db, Currency.USD, DAY, providers)

    assert providers[0].calls == 1


def test_backup_sources_are_used_in_order(db: Session, providers: list[FakeRateProvider]) -> None:
    providers[0].rate = None  # NBRB is down

    quote = get_rate(db, Currency.USD, DAY, providers)

    assert quote.source is RateSource.CBR
    assert providers[2].calls == 0


def test_offline_error_offers_nearest_history_rate(
    db: Session, offline_providers: list[FakeRateProvider]
) -> None:
    add_usd_operation(db, DAY - dt.timedelta(days=5), "3.10")
    add_usd_operation(db, DAY - dt.timedelta(days=2), "3.20")

    with pytest.raises(RateUnavailableError) as error:
        get_rate(db, Currency.USD, DAY, offline_providers)

    history = error.value.history
    assert history is not None
    assert (history.rate, history.date) == (Decimal("3.20"), DAY - dt.timedelta(days=2))
    assert "из истории" in error.value.message


def test_history_also_contains_cached_rates(db: Session) -> None:
    db.add(
        ExchangeRate(
            currency=Currency.USD,
            date=DAY - dt.timedelta(days=1),
            rate=Decimal("3.30"),
            source=RateSource.CBR,
        )
    )
    db.commit()

    history = find_history_rate(db, Currency.USD, DAY, max_days=7)

    assert history is not None
    assert (history.rate, history.source) == (Decimal("3.30"), RateSource.CBR)


def test_too_old_history_is_not_offered(
    db: Session, offline_providers: list[FakeRateProvider]
) -> None:
    add_usd_operation(db, DAY - dt.timedelta(days=8), "3.10")

    with pytest.raises(RateUnavailableError) as error:
        get_rate(db, Currency.USD, DAY, offline_providers)

    assert error.value.history is None
    assert find_history_rate(db, Currency.USD, DAY, max_days=8) is not None


def test_convert_to_byn_rounds_half_up() -> None:
    # 30.245 -> 30.25 (banker's rounding would give 30.24)
    assert convert_to_byn(Decimal("10.00"), Decimal("3.0245")) == Decimal("30.25")
