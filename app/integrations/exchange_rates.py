"""Online sources of exchange rates to BYN.

Every provider returns the number of BYN for one unit of a foreign currency on a given date.
They are queried in order: NBRB (official) -> CBR cross rate (official) -> currency-api (market).
"""

import datetime as dt
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation

import httpx

from app.models.enums import Currency, RateSource


class RateProviderError(Exception):
    """The source is unreachable or returned data that cannot be used."""


# Network failures and every way a malformed response can break parsing.
FETCH_ERRORS = (
    httpx.HTTPError,
    ET.ParseError,
    KeyError,
    TypeError,
    ValueError,
    InvalidOperation,
    ZeroDivisionError,
)


class RateProvider(ABC):
    source: RateSource

    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def get_rate(self, currency: Currency, on_date: dt.date) -> Decimal:
        """Return BYN per one unit of `currency`; raise RateProviderError on any failure."""
        try:
            rate = self._fetch(currency, on_date)
        except RateProviderError:
            raise
        except FETCH_ERRORS as exc:
            raise RateProviderError(f"{self.source.value}: {exc!r}") from exc
        if rate <= 0:
            raise RateProviderError(f"{self.source.value}: non-positive rate {rate}")
        return rate

    @abstractmethod
    def _fetch(self, currency: Currency, on_date: dt.date) -> Decimal: ...


class NbrbProvider(RateProvider):
    """National Bank of the Republic of Belarus: https://www.nbrb.by/apihelp/exrates"""

    source = RateSource.NBRB
    url = "https://api.nbrb.by/exrates/rates/{currency}"

    def _fetch(self, currency: Currency, on_date: dt.date) -> Decimal:
        response = self.client.get(
            self.url.format(currency=currency.value),
            params={"parammode": 2, "ondate": on_date.isoformat()},
        )
        response.raise_for_status()
        data = response.json()
        # The official rate is given for `Cur_Scale` units (e.g. 100 RUB), so normalize to one unit.
        return Decimal(str(data["Cur_OfficialRate"])) / Decimal(data["Cur_Scale"])


class CbrProvider(RateProvider):
    """Central Bank of Russia: rate = (currency in RUB) / (BYN in RUB)."""

    source = RateSource.CBR
    url = "https://www.cbr.ru/scripts/XML_daily.asp"

    def _fetch(self, currency: Currency, on_date: dt.date) -> Decimal:
        response = self.client.get(self.url, params={"date_req": on_date.strftime("%d/%m/%Y")})
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return self._rub_price(root, currency.value) / self._rub_price(root, "BYN")

    @staticmethod
    def _rub_price(root: ET.Element, code: str) -> Decimal:
        for valute in root.iter("Valute"):
            if valute.findtext("CharCode") == code:
                value = Decimal(valute.findtext("Value", "").replace(",", "."))
                return value / Decimal(valute.findtext("Nominal", ""))
        raise RateProviderError(f"cbr: currency {code} is missing in the response")


class CurrencyApiProvider(RateProvider):
    """Free market rates (github.com/fawazahmed0/exchange-api), served from two mirrors."""

    source = RateSource.CURRENCY_API
    mirrors = (
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/{code}.json",
        "https://{date}.currency-api.pages.dev/v1/currencies/{code}.json",
    )

    def _fetch(self, currency: Currency, on_date: dt.date) -> Decimal:
        code = currency.value.lower()
        last_error: Exception | None = None
        for template in self.mirrors:
            try:
                response = self.client.get(template.format(date=on_date.isoformat(), code=code))
                response.raise_for_status()
                return Decimal(str(response.json()[code]["byn"]))
            except FETCH_ERRORS as exc:
                last_error = exc
        raise RateProviderError(f"currency_api: all mirrors failed: {last_error!r}")


def default_providers(client: httpx.Client) -> list[RateProvider]:
    return [NbrbProvider(client), CbrProvider(client), CurrencyApiProvider(client)]
