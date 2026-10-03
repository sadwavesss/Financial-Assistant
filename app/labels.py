"""Russian display names for enum values (used by templates and API responses)."""

from app.models.enums import CategorySource, RateSource, TransactionType

TRANSACTION_TYPE_LABELS: dict[TransactionType, str] = {
    TransactionType.INCOME: "Доход",
    TransactionType.EXPENSE: "Расход",
}

RATE_SOURCE_LABELS: dict[RateSource, str] = {
    RateSource.NBRB: "НБРБ",
    RateSource.CBR: "ЦБ РФ (кросс-курс)",
    RateSource.CURRENCY_API: "currency-api",
    RateSource.MANUAL: "введён вручную",
    RateSource.HISTORY: "из истории операций",
}

CATEGORY_SOURCE_LABELS: dict[CategorySource, str] = {
    CategorySource.MANUAL: "вручную",
    CategorySource.RULE: "по правилу",
    CategorySource.ML: "ML-модель",
}
