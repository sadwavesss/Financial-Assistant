"""Parsing of real response formats of the online rate sources (network is mocked)."""

import datetime as dt
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest

from app.integrations.exchange_rates import (
    CbrProvider,
    CurrencyApiProvider,
    NbrbProvider,
    RateProviderError,
)
from app.models import Currency

DAY = dt.date(2026, 9, 15)

CBR_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="15.09.2026" name="Foreign Currency Market">
  <Valute ID="R01090B"><NumCode>933</NumCode><CharCode>BYN</CharCode><Nominal>1</Nominal>
    <Name>Белорусский рубль</Name><Value>27,8706</Value></Valute>
  <Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal>
    <Name>Доллар США</Name><Value>84,3363</Value></Valute>
</ValCurs>""".encode("cp1251")


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_nbrb_rate_is_normalized_by_scale() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/exrates/rates/USD"
        assert request.url.params["parammode"] == "2"
        assert request.url.params["ondate"] == "2026-09-15"
        return httpx.Response(200, json={"Cur_Scale": 1, "Cur_OfficialRate": 3.026})

    assert NbrbProvider(make_client(handler)).get_rate(Currency.USD, DAY) == Decimal("3.026")


def test_nbrb_scale_greater_than_one() -> None:
    client = make_client(
        lambda _: httpx.Response(200, json={"Cur_Scale": 100, "Cur_OfficialRate": 3.5888})
    )

    assert NbrbProvider(client).get_rate(Currency.USD, DAY) == Decimal("0.035888")


def test_cbr_cross_rate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["date_req"] == "15/09/2026"
        return httpx.Response(200, content=CBR_XML)

    rate = CbrProvider(make_client(handler)).get_rate(Currency.USD, DAY)

    assert rate.quantize(Decimal("0.0001")) == Decimal("3.0260")


def test_currency_api_falls_back_to_mirror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.jsdelivr.net":
            return httpx.Response(503)
        return httpx.Response(200, json={"date": "2026-09-15", "usd": {"byn": 3.04162245}})

    rate = CurrencyApiProvider(make_client(handler)).get_rate(Currency.USD, DAY)

    assert rate == Decimal("3.04162245")


@pytest.mark.parametrize(
    ("provider_cls", "response"),
    [
        (NbrbProvider, httpx.Response(404)),
        (NbrbProvider, httpx.Response(200, text="not json")),
        (NbrbProvider, httpx.Response(200, json={"Cur_Scale": 1, "Cur_OfficialRate": 0})),
        (CbrProvider, httpx.Response(200, content=b"<ValCurs></ValCurs>")),
        (CbrProvider, httpx.Response(200, content=b"<broken")),
        (CurrencyApiProvider, httpx.Response(200, json={"usd": {}})),
    ],
)
def test_bad_responses_raise_provider_error(provider_cls, response: httpx.Response) -> None:
    provider = provider_cls(make_client(lambda _: response))

    with pytest.raises(RateProviderError):
        provider.get_rate(Currency.USD, DAY)


def test_network_failure_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no internet", request=request)

    with pytest.raises(RateProviderError):
        NbrbProvider(make_client(handler)).get_rate(Currency.USD, DAY)
