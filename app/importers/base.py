"""Common interface of file importers (Strategy pattern).

An importer only turns a file into validated rows; duplicates, exchange rates and saving
are handled by `app.services.imports`. A new format (Excel, a bank statement) is a new
subclass registered in `app.importers.IMPORTERS`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.schemas.transaction import TransactionIn
from app.services.errors import InvalidDataError
from app.utils.validation import humanize_errors

FIELD_LABELS = {
    "date": "Дата",
    "type": "Тип",
    "amount": "Сумма",
    "currency": "Валюта",
    "description": "Описание",
    "category": "Категория",
}


class ImportFileError(InvalidDataError):
    """The whole file cannot be read (encoding, missing columns, too large, empty)."""

    code = "import_file_error"


@dataclass(frozen=True)
class ParsedRow:
    line: int  # line number in the file, as the user sees it in a text editor
    data: TransactionIn
    category_name: str | None = None


@dataclass(frozen=True)
class RowError:
    line: int
    message: str


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)


class StatementImporter(ABC):
    name: str  # identifier used in URLs and forms, e.g. "csv"
    label: str  # shown to the user
    extensions: tuple[str, ...]

    @abstractmethod
    def parse(self, content: bytes) -> ParseResult:
        """Parse the file; raise ImportFileError if it cannot be processed at all."""

    @staticmethod
    def validate_row(line: int, values: dict[str, str]) -> TransactionIn | RowError:
        """Validate one row with the same rules as manual input (TransactionIn)."""
        try:
            return TransactionIn.model_validate(values)
        except ValidationError as exc:
            problems = [
                f"{FIELD_LABELS.get(name, name)}: {message[:1].lower()}{message[1:]}"
                for name, message in humanize_errors(exc).items()
            ]
            return RowError(line, "; ".join(problems))
