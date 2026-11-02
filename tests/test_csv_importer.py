"""CSV parsing: encodings, separators, formats of dates and amounts, row-level errors."""

import datetime as dt
from decimal import Decimal

import pytest

from app.importers import ImportFileError
from app.importers.csv_importer import TEMPLATE, CsvImporter
from app.models import Currency, TransactionType

importer = CsvImporter()


def parse(text: str, encoding: str = "utf-8"):
    return importer.parse(text.encode(encoding))


def test_template_is_valid() -> None:
    result = parse(TEMPLATE)

    assert result.errors == []
    assert len(result.rows) == 4
    salary, groceries, coffee, steam = result.rows
    assert (salary.data.type, salary.data.amount) == (TransactionType.INCOME, Decimal("1500.00"))
    assert groceries.category_name == "Продукты"
    assert coffee.category_name is None
    assert steam.data.currency is Currency.USD
    assert [row.line for row in result.rows] == [2, 3, 4, 5]


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1251"])
def test_encodings(encoding: str) -> None:
    result = parse("Дата;Сумма;Описание\n01.10.2026;-5,00;Кофе\n", encoding)

    assert result.rows[0].data.description == "Кофе"


@pytest.mark.parametrize("separator", [";", ",", "\t"])
def test_separators(separator: str) -> None:
    text = separator.join(["date", "amount", "description"]) + "\n"
    text += separator.join(["2026-10-01", "-5.00", "Coffee"]) + "\n"

    assert parse(text).rows[0].data.amount == Decimal("5.00")


def test_header_aliases_any_order_and_quoted_values() -> None:
    result = parse('Описание,Сумма,Дата\n"Евроопт, Минск","1 234,56",01.10.2026\n')

    row = result.rows[0].data
    assert (row.description, row.amount) == ("Евроопт, Минск", Decimal("1234.56"))


def test_sign_defines_type_without_type_column() -> None:
    result = parse("Дата;Сумма\n01.10.2026;-10\n01.10.2026;250\n")

    assert [row.data.type for row in result.rows] == [
        TransactionType.EXPENSE,
        TransactionType.INCOME,
    ]
    assert all(row.data.amount > 0 for row in result.rows)


@pytest.mark.parametrize("value", ["2026-10-01", "01.10.2026", "01.10.26", "01/10/2026"])
def test_date_formats(value: str) -> None:
    assert parse(f"Дата;Сумма\n{value};-1\n").rows[0].data.date == dt.date(2026, 10, 1)


def test_row_errors_do_not_stop_other_rows() -> None:
    future = (dt.date.today() + dt.timedelta(days=3)).strftime("%d.%m.%Y")
    text = (
        "Дата;Тип;Сумма;Валюта\n"
        "01.10.2026;расход;10;BYN\n"  # line 2: ok
        "31.02.2026;расход;10;BYN\n"  # line 3: impossible date
        "01.10.2026;расход;abc;BYN\n"  # line 4: not a number
        "01.10.2026;перевод;10;BYN\n"  # line 5: unknown type
        "01.10.2026;расход;10;EUR\n"  # line 6: unsupported currency
        f"{future};расход;10;BYN\n"  # line 7: future date
        "01.10.2026;расход;0;BYN\n"  # line 8: zero amount
        "01.10.2026;расход;1,234;BYN\n"  # line 9: three decimals
    )

    result = parse(text)

    assert [row.line for row in result.rows] == [2]
    errors = {error.line: error.message for error in result.errors}
    assert sorted(errors) == [3, 4, 5, 6, 7, 8, 9]
    assert errors[3].startswith("Дата")
    assert errors[4].startswith("Сумма")
    assert "доход" in errors[5]
    assert errors[6].startswith("Валюта")
    assert "будущем" in errors[7]
    assert "больше нуля" in errors[8]
    assert "2 знаков" in errors[9]


def test_long_description_is_truncated() -> None:
    result = parse(f"Дата;Сумма;Описание\n01.10.2026;-1;{'x' * 400}\n")

    assert len(result.rows[0].data.description) == 255


def test_blank_lines_are_ignored() -> None:
    assert len(parse("Дата;Сумма\n\n01.10.2026;-1\n;\n").rows) == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "пуст"),
        ("Дата;Сумма\n", "только заголовок"),
        ("Дата;Описание\n01.10.2026;Кофе\n", "«Сумма»"),
    ],
)
def test_unreadable_files(text: str, message: str) -> None:
    with pytest.raises(ImportFileError, match=message):
        parse(text)
