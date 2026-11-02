"""CSV importer for the application's own template.

Template (columns may go in any order; header names in Russian or English):

    Дата;Тип;Сумма;Валюта;Описание;Категория
    15.09.2026;расход;12,50;BYN;Евроопт;Продукты

- required columns: date, amount; others are optional;
- without the type column the sign of the amount decides: negative = expense;
- dates: 2026-09-15, 15.09.2026, 15.09.26, 15/09/2026;
- amounts: "1 234,56", "1234.56", "-12,50";
- encoding UTF-8 (with or without BOM) or Windows-1251; separator ";", "," or tab.
"""

import csv
import datetime as dt
import io
from decimal import Decimal, InvalidOperation

from app.importers.base import (
    FIELD_LABELS,
    ImportFileError,
    ParsedRow,
    ParseResult,
    RowError,
    StatementImporter,
)
from app.models import TransactionType
from app.utils.text import normalize_text

HEADER_ALIASES = {
    "date": {"date", "дата", "дата операции"},
    "type": {"type", "тип", "тип операции"},
    "amount": {"amount", "сумма", "сумма операции"},
    "currency": {"currency", "валюта"},
    "description": {"description", "описание", "назначение", "комментарий"},
    "category": {"category", "категория"},
}
REQUIRED_COLUMNS = ("date", "amount")
TYPE_ALIASES = {
    "income": TransactionType.INCOME,
    "доход": TransactionType.INCOME,
    "expense": TransactionType.EXPENSE,
    "расход": TransactionType.EXPENSE,
}
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y")
DELIMITERS = (";", ",", "\t")
MAX_DESCRIPTION = 255

# Example file offered for download on the import page (opens correctly in Excel: ";" + BOM).
TEMPLATE = (
    "Дата;Тип;Сумма;Валюта;Описание;Категория\n"
    "01.10.2026;доход;1500,00;BYN;Зарплата за сентябрь;Зарплата\n"
    "02.10.2026;расход;45,30;BYN;Евроопт, продукты;Продукты\n"
    "03.10.2026;расход;12,50;BYN;Кофейня у метро;\n"
    "05.10.2026;расход;9,99;USD;Steam, игра;Развлечения и досуг\n"
)


class CsvImporter(StatementImporter):
    name = "csv"
    label = "CSV (шаблон приложения)"
    extensions = (".csv", ".txt")

    def parse(self, content: bytes) -> ParseResult:
        text = _decode(content)
        lines = text.splitlines()
        if not lines or not lines[0].strip():
            raise ImportFileError("Файл пуст.")

        delimiter = max(DELIMITERS, key=lines[0].count)
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        columns = _map_columns(next(reader))

        result = ParseResult()
        for line, cells in enumerate(reader, start=2):
            if not any(cell.strip() for cell in cells):
                continue  # blank line
            raw = {
                key: cells[index].strip() if index < len(cells) else ""
                for key, index in columns.items()
            }
            parsed = self._parse_row(line, raw)
            (result.errors if isinstance(parsed, RowError) else result.rows).append(parsed)

        if not result.rows and not result.errors:
            raise ImportFileError("В файле нет операций — только заголовок.")
        return result

    def _parse_row(self, line: int, raw: dict[str, str]) -> ParsedRow | RowError:
        amount = _parse_amount(raw["amount"])
        if amount is None:
            return RowError(line, f"Сумма: не удалось распознать число «{raw['amount']}»")

        type_text = normalize_text(raw.get("type", ""))
        if type_text:
            if type_text not in TYPE_ALIASES:
                return RowError(line, f"Тип: «{raw['type']}» — ожидается «доход» или «расход»")
            transaction_type = TYPE_ALIASES[type_text]
        else:
            transaction_type = TransactionType.EXPENSE if amount < 0 else TransactionType.INCOME

        on_date = _parse_date(raw["date"])
        if on_date is None:
            return RowError(line, f"Дата: не удалось распознать «{raw['date']}»")

        description = raw.get("description", "")
        if len(description) > MAX_DESCRIPTION:
            description = description[: MAX_DESCRIPTION - 1] + "…"

        values = {
            "date": on_date.isoformat(),
            "type": transaction_type.value,
            "amount": str(abs(amount)),
            "description": description,
        }
        if raw.get("currency"):
            values["currency"] = raw["currency"].upper()

        validated = self.validate_row(line, values)
        if isinstance(validated, RowError):
            return validated
        return ParsedRow(line, validated, raw.get("category") or None)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1251")


def _map_columns(header: list[str]) -> dict[str, int]:
    """Map known header names to column indexes; fail if a required column is missing."""
    columns: dict[str, int] = {}
    for index, name in enumerate(header):
        normalized = normalize_text(name)
        for key, aliases in HEADER_ALIASES.items():
            if normalized in aliases and key not in columns:
                columns[key] = index
    missing = [key for key in REQUIRED_COLUMNS if key not in columns]
    if missing:
        names = ", ".join(f"«{FIELD_LABELS[key]}»" for key in missing)
        raise ImportFileError(
            f"В заголовке файла нет обязательных столбцов: {names}. "
            "Скачайте шаблон на странице импорта."
        )
    return columns


def _parse_amount(text: str) -> Decimal | None:
    cleaned = text.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned) if cleaned else None
    except InvalidOperation:
        return None


def _parse_date(text: str) -> dt.date | None:
    for date_format in DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None
