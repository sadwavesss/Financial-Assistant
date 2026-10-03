"""Financial transactions (operations)."""

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import CategorySource, Currency, TransactionType, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("exchange_rate > 0", name="exchange_rate_positive"),
        CheckConstraint("amount_byn > 0", name="amount_byn_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    type: Mapped[TransactionType] = mapped_column(enum_type(TransactionType, "transaction_type"))

    # The amount is always positive; the direction of money flow is defined by `type`.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[Currency] = mapped_column(
        enum_type(Currency, "currency"), default=Currency.BYN
    )
    # BYN per one unit of `currency` on `date` (1 for BYN).
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal(1))
    # Amount converted to BYN: all analytics are calculated in this column.
    amount_byn: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    description: Mapped[str] = mapped_column(String(255), default="")

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    category_source: Mapped[CategorySource | None] = mapped_column(
        enum_type(CategorySource, "category_source")
    )

    # Fingerprint of an imported row; prevents importing the same operation twice.
    import_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

    category: Mapped["Category | None"] = relationship(back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"Transaction(id={self.id}, date={self.date}, type={self.type.value}, "
            f"amount={self.amount} {self.currency.value})"
        )
