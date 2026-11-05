"""Financial transactions (operations)."""

import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Numeric, String, false
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database import Base
from app.models.enums import CategorySource, Currency, RateSource, TransactionType, enum_type
from app.models.mixins import TimestampMixin
from app.utils.text import normalize_text

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
    # Where the rate came from; NULL for BYN operations (no conversion needed).
    rate_source: Mapped[RateSource | None] = mapped_column(enum_type(RateSource, "rate_source"))
    # Amount converted to BYN: all analytics are calculated in this column.
    amount_byn: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    description: Mapped[str] = mapped_column(String(255), default="")
    # Lower-cased copy for case-insensitive search: SQLite LIKE ignores case only for Latin.
    description_normalized: Mapped[str] = mapped_column(String(255), default="", server_default="")

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True
    )
    category_source: Mapped[CategorySource | None] = mapped_column(
        enum_type(CategorySource, "category_source")
    )
    # Confidence of the automatic decision (0..1); NULL for manual categories.
    category_confidence: Mapped[float | None]
    # The automatic decision is doubtful (conflict, low confidence): the user should check it.
    needs_review: Mapped[bool] = mapped_column(default=False, server_default=false(), index=True)
    # Step-by-step protocol of the automatic decision (rules, model, arbitration), see
    # app.services.categorization.Decision.trace.
    categorization_trace: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Fingerprint of an imported row; prevents importing the same operation twice.
    import_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

    category: Mapped["Category | None"] = relationship(back_populates="transactions")

    @validates("description")
    def _sync_normalized_description(self, _key: str, value: str) -> str:
        self.description_normalized = normalize_text(value)
        return value

    def __repr__(self) -> str:
        return (
            f"Transaction(id={self.id}, date={self.date}, type={self.type.value}, "
            f"amount={self.amount} {self.currency.value})"
        )
