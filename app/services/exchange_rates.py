"""Exchange rate resolution: local cache -> online sources -> the system's own history.

1. A rate already known for the exact date is taken from the `exchange_rates` table.
2. Otherwise online sources are queried in order; the first successful answer is cached.
3. If all sources fail, `RateUnavailableError` is raised. It carries the nearest rate from
   the local history (cached rates and past USD operations, no Internet needed) if it is not
   older/newer than `rate_history_max_days`, so the user can choose it or type a rate manually.
"""

import datetime as dt
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations.exchange_rates import RateProvider, RateProviderError
from app.models import Currency, ExchangeRate, RateSource, Transaction
from app.services.errors import InvalidDataError, ServiceError

logger = logging.getLogger(__name__)

RATE_PRECISION = Decimal("0.000001")
MONEY_PRECISION = Decimal("0.01")


@dataclass(frozen=True)
class RateQuote:
    currency: Currency
    rate: Decimal
    source: RateSource
    date: dt.date  # the date the rate belongs to (for history it may differ from the request)

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency.value,
            "rate": str(self.rate),
            "source": self.source.value,
            "date": self.date.isoformat(),
        }


class RateUnavailableError(ServiceError):
    status_code = 422
    code = "rate_unavailable"

    def __init__(self, message: str, history: RateQuote | None) -> None:
        super().__init__(message)
        self.history = history

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "history": self.history.to_dict() if self.history else None}


def convert_to_byn(amount: Decimal, rate: Decimal) -> Decimal:
    return (amount * rate).quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP)


def get_rate(
    db: Session, currency: Currency, on_date: dt.date, providers: Sequence[RateProvider]
) -> RateQuote:
    """Return the rate of `currency` to BYN on `on_date` or raise RateUnavailableError."""
    if currency is Currency.BYN:
        raise InvalidDataError("Для операций в BYN курс не нужен.", field="currency")

    cached = _find_cached(db, currency, on_date)
    if cached:
        return _quote_from_cache(cached)

    for provider in providers:
        try:
            rate = provider.get_rate(currency, on_date).quantize(RATE_PRECISION)
        except RateProviderError as exc:
            logger.warning("Exchange rate source failed: %s", exc)
            continue
        return _save_to_cache(db, RateQuote(currency, rate, provider.source, on_date))

    history = find_history_rate(db, currency, on_date)
    hint = " или используйте курс из истории" if history else ""
    raise RateUnavailableError(
        f"Не удалось получить курс {currency.value} на {on_date:%d.%m.%Y}: "
        f"источники курсов недоступны. Введите курс вручную{hint}.",
        history,
    )


def find_history_rate(
    db: Session, currency: Currency, on_date: dt.date, max_days: int | None = None
) -> RateQuote | None:
    """Nearest rate known to the system (cache or past operations) within `max_days`."""
    if max_days is None:
        max_days = get_settings().rate_history_max_days
    start, end = on_date - dt.timedelta(days=max_days), on_date + dt.timedelta(days=max_days)

    cached = db.scalars(
        select(ExchangeRate).where(
            ExchangeRate.currency == currency, ExchangeRate.date.between(start, end)
        )
    )
    operations = db.scalars(
        select(Transaction).where(
            Transaction.currency == currency, Transaction.date.between(start, end)
        )
    )
    candidates = [_quote_from_cache(row) for row in cached] + [
        RateQuote(currency, row.exchange_rate, row.rate_source or RateSource.MANUAL, row.date)
        for row in operations
    ]
    if not candidates:
        return None
    # Closest date wins; on equal distance an earlier date is preferred.
    return min(candidates, key=lambda quote: (abs((quote.date - on_date).days), quote.date))


def _find_cached(db: Session, currency: Currency, on_date: dt.date) -> ExchangeRate | None:
    return db.scalar(
        select(ExchangeRate).where(ExchangeRate.currency == currency, ExchangeRate.date == on_date)
    )


def _quote_from_cache(row: ExchangeRate) -> RateQuote:
    return RateQuote(row.currency, row.rate, row.source, row.date)


def _save_to_cache(db: Session, quote: RateQuote) -> RateQuote:
    db.add(
        ExchangeRate(currency=quote.currency, date=quote.date, rate=quote.rate, source=quote.source)
    )
    try:
        db.commit()
    except IntegrityError:
        # The same rate was saved by a parallel request: keep the stored one.
        db.rollback()
        stored = _find_cached(db, quote.currency, quote.date)
        return _quote_from_cache(stored) if stored else quote
    return quote
