"""Cached exchange rates of foreign currencies to BYN."""

import datetime as dt
from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import Currency, RateSource, enum_type
from app.models.mixins import TimestampMixin


class ExchangeRate(TimestampMixin, Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("currency", "date"),
        CheckConstraint("rate > 0", name="rate_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[Currency] = mapped_column(enum_type(Currency, "rate_currency"))
    date: Mapped[dt.date]
    # BYN per one unit of `currency` (NBRB rate divided by its scale).
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    source: Mapped[RateSource] = mapped_column(enum_type(RateSource, "rate_source"))

    def __repr__(self) -> str:
        return f"ExchangeRate({self.currency.value} {self.date}: {self.rate})"
