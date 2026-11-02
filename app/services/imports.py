"""Import of transactions from files: preview, duplicate detection and saving.

1. The importer parses the file into validated rows (or row errors).
2. Every row gets a fingerprint (`import_hash`); rows already imported earlier are duplicates.
   Identical rows inside one file (two coffees for the same price on the same day) are
   kept apart by their occurrence number, so both are imported, but only once.
3. On confirmation USD rows get the rate (cache -> online sources -> history), and all new
   rows are saved in a single database transaction.
"""

import datetime as dt
import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.importers import ImportFileError, ParsedRow, RowError, StatementImporter
from app.integrations.exchange_rates import RateProvider
from app.models import (
    Category,
    CategorySource,
    Currency,
    RateSource,
    Transaction,
    TransactionType,
)
from app.services.exchange_rates import RateUnavailableError, convert_to_byn, get_rate
from app.utils.text import normalize_text


class RowStatus(StrEnum):
    NEW = "new"
    DUPLICATE = "duplicate"
    ERROR = "error"


@dataclass
class PreviewRow:
    line: int
    status: RowStatus
    row: ParsedRow | None = None
    category: Category | None = None
    import_hash: str | None = None
    message: str | None = None  # error text or a warning for a new row


@dataclass
class ImportPreview:
    rows: list[PreviewRow]

    def count(self, status: RowStatus) -> int:
        return sum(1 for row in self.rows if row.status is status)

    @property
    def new_rows(self) -> list[PreviewRow]:
        return [row for row in self.rows if row.status is RowStatus.NEW]


@dataclass
class ImportReport:
    created: int = 0
    duplicates: int = 0
    errors: list[RowError] = field(default_factory=list)


def preview_import(db: Session, content: bytes, importer: StatementImporter) -> ImportPreview:
    """Parse the file and classify every row as new, duplicate or erroneous (nothing is saved)."""
    settings = get_settings()
    if len(content) > settings.import_max_bytes:
        limit_mb = settings.import_max_bytes // (1024 * 1024)
        raise ImportFileError(f"Файл больше {limit_mb} МБ.")

    parsed = importer.parse(content)
    total = len(parsed.rows) + len(parsed.errors)
    if total > settings.import_max_rows:
        raise ImportFileError(f"В файле больше {settings.import_max_rows} строк.")

    hashes = _fingerprints(parsed.rows)
    known = _existing_hashes(db, hashes)
    categories = _categories_by_name(db)

    rows = [
        PreviewRow(error.line, RowStatus.ERROR, message=error.message) for error in parsed.errors
    ]
    for row, import_hash in zip(parsed.rows, hashes, strict=True):
        if import_hash in known:
            rows.append(PreviewRow(row.line, RowStatus.DUPLICATE, row, import_hash=import_hash))
            continue
        category, warning = None, None
        if row.category_name:
            category = categories.get((normalize_text(row.category_name), row.data.type))
            if category is None:
                warning = (
                    f"Категория «{row.category_name}» не найдена — операция будет без категории"
                )
        rows.append(PreviewRow(row.line, RowStatus.NEW, row, category, import_hash, warning))

    rows.sort(key=lambda item: item.line)
    return ImportPreview(rows)


def run_import(
    db: Session,
    content: bytes,
    importer: StatementImporter,
    providers: Sequence[RateProvider],
) -> ImportReport:
    """Save all new rows of the file; rows without an obtainable rate become errors."""
    preview = preview_import(db, content, importer)
    report = ImportReport(
        duplicates=preview.count(RowStatus.DUPLICATE),
        errors=[
            RowError(row.line, row.message or "")
            for row in preview.rows
            if row.status is RowStatus.ERROR
        ],
    )

    # Rates first: get_rate commits its cache, so it must not run in the middle of the import.
    rates = _resolve_rates(db, preview.new_rows, providers)

    for item in preview.new_rows:
        data = item.row.data
        rate_info = rates.get((data.currency, data.date))
        if data.currency is not Currency.BYN and rate_info is None:
            report.errors.append(
                RowError(
                    item.line, f"Курс {data.currency.value} на {data.date:%d.%m.%Y} недоступен"
                )
            )
            continue
        rate, rate_source = rate_info or (Decimal(1), None)
        db.add(
            Transaction(
                date=data.date,
                type=data.type,
                amount=data.amount,
                currency=data.currency,
                exchange_rate=rate,
                rate_source=rate_source,
                amount_byn=convert_to_byn(data.amount, rate),
                description=data.description,
                category=item.category,
                category_source=CategorySource.MANUAL if item.category else None,
                import_hash=item.import_hash,
            )
        )
        report.created += 1

    db.commit()
    report.errors.sort(key=lambda error: error.line)
    return report


def _fingerprints(rows: Sequence[ParsedRow]) -> list[str]:
    seen: Counter[str] = Counter()
    hashes = []
    for row in rows:
        data = row.data
        key = (
            f"{data.date.isoformat()}|{data.type.value}|{data.amount:.2f}|"
            f"{data.currency.value}|{normalize_text(data.description)}"
        )
        hashes.append(hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest())
        seen[key] += 1
    return hashes


def _existing_hashes(db: Session, hashes: Sequence[str]) -> set[str]:
    found: set[str] = set()
    for start in range(0, len(hashes), 500):  # stay well below SQL parameter limits
        chunk = hashes[start : start + 500]
        found.update(
            db.scalars(select(Transaction.import_hash).where(Transaction.import_hash.in_(chunk)))
        )
    return found


def _categories_by_name(db: Session) -> dict[tuple[str, TransactionType], Category]:
    return {(normalize_text(c.name), c.type): c for c in db.scalars(select(Category))}


RateKey = tuple[Currency, dt.date]
RateValue = tuple[Decimal, RateSource]


def _resolve_rates(
    db: Session, rows: Sequence[PreviewRow], providers: Sequence[RateProvider]
) -> dict[RateKey, RateValue]:
    """One rate per (currency, date): online/cached, otherwise the nearest one from history."""
    needed = {
        (item.row.data.currency, item.row.data.date)
        for item in rows
        if item.row.data.currency is not Currency.BYN
    }
    rates: dict[RateKey, RateValue] = {}
    for currency, on_date in sorted(needed, key=lambda pair: pair[1]):
        try:
            quote = get_rate(db, currency, on_date, providers)
            rates[(currency, on_date)] = (quote.rate, quote.source)
        except RateUnavailableError as exc:
            if exc.history:
                rates[(currency, on_date)] = (exc.history.rate, RateSource.HISTORY)
    return rates
