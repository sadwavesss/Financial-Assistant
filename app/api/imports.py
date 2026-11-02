"""REST API for importing transactions from files."""

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.dependencies import DbSession, RateProviders, read_upload
from app.importers import get_importer
from app.importers.csv_importer import TEMPLATE
from app.schemas.imports import ImportPreviewOut, ImportReportOut
from app.services.imports import preview_import, run_import

router = APIRouter(prefix="/imports", tags=["Импорт"])

FormatQuery = Annotated[str, Query(alias="format", description="Формат файла")]
UploadedFile = Annotated[UploadFile, File(description="Файл с операциями")]


@router.get("/template.csv", summary="Скачать шаблон CSV")
def download_template() -> Response:
    # BOM makes Excel recognise UTF-8 and show Cyrillic correctly.
    return Response(
        content="\ufeff" + TEMPLATE,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="template.csv"'},
    )


@router.post("/preview", response_model=ImportPreviewOut, summary="Предпросмотр импорта")
async def preview(db: DbSession, file: UploadedFile, file_format: FormatQuery = "csv"):
    content = await read_upload(file)
    return ImportPreviewOut.from_preview(preview_import(db, content, get_importer(file_format)))


@router.post("", response_model=ImportReportOut, summary="Импортировать операции из файла")
async def import_file(
    db: DbSession, providers: RateProviders, file: UploadedFile, file_format: FormatQuery = "csv"
):
    content = await read_upload(file)
    report = run_import(db, content, get_importer(file_format), providers)
    return ImportReportOut.from_report(report)
