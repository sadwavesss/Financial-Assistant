"""Helpers shared by tests."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.exchange_rates import RateProvider, RateProviderError
from app.models import Category, Currency, RateSource, TransactionType

ONLINE_SOURCES = (RateSource.NBRB, RateSource.CBR, RateSource.CURRENCY_API)


class FakeRateProvider(RateProvider):
    """Offline rate source: returns a fixed rate or fails (rate=None) and counts calls."""

    def __init__(self, source: RateSource, rate: str | None) -> None:  # no HTTP client needed
        self.source = source
        self.rate = rate
        self.calls = 0

    def _fetch(self, currency: Currency, on_date: dt.date) -> Decimal:
        self.calls += 1
        if self.rate is None:
            raise RateProviderError(f"{self.source.value} is down")
        return Decimal(self.rate)


def category_id(db: Session, name: str, transaction_type: TransactionType) -> int:
    return db.scalar(
        select(Category.id).where(Category.name == name, Category.type == transaction_type)
    )
