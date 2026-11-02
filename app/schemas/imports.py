"""Schemas of file import responses."""

import datetime as dt
from decimal import Decimal

from pydantic import BaseModel

from app.models import Currency, TransactionType
from app.services.imports import ImportPreview, ImportReport, RowStatus


class RowErrorOut(BaseModel):
    line: int
    message: str


class PreviewRowOut(BaseModel):
    line: int
    status: RowStatus
    date: dt.date | None = None
    type: TransactionType | None = None
    amount: Decimal | None = None
    currency: Currency | None = None
    description: str | None = None
    category: str | None = None
    message: str | None = None


class ImportPreviewOut(BaseModel):
    new: int
    duplicates: int
    errors: int
    rows: list[PreviewRowOut]

    @classmethod
    def from_preview(cls, preview: ImportPreview) -> "ImportPreviewOut":
        rows = []
        for item in preview.rows:
            data = item.row.data if item.row else None
            rows.append(
                PreviewRowOut(
                    line=item.line,
                    status=item.status,
                    date=data.date if data else None,
                    type=data.type if data else None,
                    amount=data.amount if data else None,
                    currency=data.currency if data else None,
                    description=data.description if data else None,
                    category=item.category.name if item.category else None,
                    message=item.message,
                )
            )
        return cls(
            new=preview.count(RowStatus.NEW),
            duplicates=preview.count(RowStatus.DUPLICATE),
            errors=preview.count(RowStatus.ERROR),
            rows=rows,
        )


class ImportReportOut(BaseModel):
    created: int
    duplicates: int
    errors: list[RowErrorOut]

    @classmethod
    def from_report(cls, report: ImportReport) -> "ImportReportOut":
        return cls(
            created=report.created,
            duplicates=report.duplicates,
            errors=[RowErrorOut(line=e.line, message=e.message) for e in report.errors],
        )
