"""Transaction schemas: input validation, filters and API responses."""

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.models import CategorySource, Currency, RateSource, TransactionType
from app.schemas.category import CategoryBrief

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Rate = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=6)]


class RateMode(StrEnum):
    """How to get the exchange rate for a foreign currency operation."""

    AUTO = "auto"  # cache or online sources
    MANUAL = "manual"  # use `manual_rate`
    HISTORY = "history"  # nearest rate from the system's own history


class TransactionIn(BaseModel):
    """Data for creating or fully updating a transaction."""

    model_config = ConfigDict(str_strip_whitespace=True)

    date: dt.date
    type: TransactionType
    amount: Money
    currency: Currency = Currency.BYN
    description: str = Field(default="", max_length=255)
    category_id: int | None = None
    rate_mode: RateMode = RateMode.AUTO
    # validate_default: the check below must run even when the field is omitted.
    manual_rate: Rate | None = Field(default=None, validate_default=True)

    @field_validator("date")
    @classmethod
    def not_in_future(cls, value: dt.date) -> dt.date:
        if value > dt.date.today():
            raise ValueError("Дата операции не может быть в будущем")
        return value

    @field_validator("manual_rate")
    @classmethod
    def manual_rate_required(cls, value: Decimal | None, info: ValidationInfo) -> Decimal | None:
        # Fields are validated in declaration order, so currency and rate_mode are known here.
        needs_rate = (
            info.data.get("currency", Currency.BYN) is not Currency.BYN
            and info.data.get("rate_mode") is RateMode.MANUAL
        )
        if needs_rate and value is None:
            raise ValueError("Укажите курс вручную")
        return value


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    type: TransactionType
    amount: Decimal
    currency: Currency
    exchange_rate: Decimal
    rate_source: RateSource | None
    amount_byn: Decimal
    description: str
    category: CategoryBrief | None
    category_source: CategorySource | None
    category_confidence: float | None
    needs_review: bool
    categorization_trace: dict[str, Any] | None
    created_at: dt.datetime
    updated_at: dt.datetime


class TransactionFilters(BaseModel):
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    type: TransactionType | None = None
    category_id: int | None = None
    needs_review: bool | None = None
    search: str | None = Field(default=None, max_length=100)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @model_validator(mode="after")
    def period_is_valid(self) -> Self:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Начало периода позже его конца")
        return self


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int
    pages: int
    income_byn: Decimal
    expense_byn: Decimal


class RateQuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: Currency
    date: dt.date
    rate: Decimal
    source: RateSource
    source_label: str
