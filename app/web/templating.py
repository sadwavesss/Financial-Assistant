"""Jinja2 environment shared by all HTML pages: globals and formatting filters."""

import datetime as dt
from decimal import Decimal

from fastapi.templating import Jinja2Templates

from app import __version__
from app.config import TEMPLATES_DIR, get_settings
from app.labels import CATEGORY_SOURCE_LABELS, RATE_SOURCE_LABELS, TRANSACTION_TYPE_LABELS
from app.utils.formatting import format_money


def format_money_float(value: float | None) -> str:
    """Same as `money` for float values coming from statistical models."""
    return format_money(Decimal(str(round(value, 2)))) if value is not None else ""


def format_rate(value: Decimal | None) -> str:
    """Decimal("3.250000") -> "3,25": no trailing zeros, at least two decimals."""
    if value is None:
        return ""
    text = f"{value.normalize():f}"
    whole, _, fraction = text.partition(".")
    return f"{whole},{fraction.ljust(2, '0')}"


def format_date(value: dt.date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals.update(
    app_name=get_settings().app_name,
    app_version=__version__,
    type_labels=TRANSACTION_TYPE_LABELS,
    rate_source_labels=RATE_SOURCE_LABELS,
    category_source_labels=CATEGORY_SOURCE_LABELS,
)
templates.env.filters.update(
    money=format_money, money_float=format_money_float, rate=format_rate, date_ru=format_date
)
