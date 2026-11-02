"""File importers. To support a new format, implement `StatementImporter` and register it here."""

from app.importers.base import ImportFileError, ParsedRow, ParseResult, RowError, StatementImporter
from app.importers.csv_importer import CsvImporter

IMPORTERS: dict[str, StatementImporter] = {importer.name: importer for importer in (CsvImporter(),)}


def get_importer(file_format: str) -> StatementImporter:
    if file_format not in IMPORTERS:
        supported = ", ".join(IMPORTERS)
        raise ImportFileError(f"Формат «{file_format}» не поддерживается. Доступные: {supported}.")
    return IMPORTERS[file_format]


__all__ = [
    "IMPORTERS",
    "ImportFileError",
    "ParseResult",
    "ParsedRow",
    "RowError",
    "StatementImporter",
    "get_importer",
]
