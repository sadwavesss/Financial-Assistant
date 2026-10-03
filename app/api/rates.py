"""REST API for exchange rates."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import DbSession, RateProviders
from app.labels import RATE_SOURCE_LABELS
from app.models import Currency
from app.schemas.transaction import RateQuoteOut
from app.services.exchange_rates import get_rate

router = APIRouter(prefix="/rates", tags=["Курсы валют"])


@router.get(
    "/{currency}",
    response_model=RateQuoteOut,
    summary="Курс валюты к BYN на дату",
    description=(
        "Источники по порядку: кэш, НБРБ, ЦБ РФ (кросс-курс), currency-api. "
        "Если все недоступны — ошибка `rate_unavailable` с ближайшим курсом из истории."
    ),
)
def read_rate(
    currency: Currency,
    db: DbSession,
    providers: RateProviders,
    on_date: Annotated[dt.date, Query(alias="date")],
) -> RateQuoteOut:
    quote = get_rate(db, currency, on_date, providers)
    return RateQuoteOut(
        currency=quote.currency,
        date=quote.date,
        rate=quote.rate,
        source=quote.source,
        source_label=RATE_SOURCE_LABELS[quote.source],
    )
