"""HTML pages for importing transactions: upload -> preview -> confirm."""

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.dependencies import DbSession, RateProviders, read_upload
from app.importers import IMPORTERS, ImportFileError, get_importer
from app.services.imports import RowStatus, preview_import, run_import
from app.web import upload_store
from app.web.templating import templates

router = APIRouter(prefix="/import")

# Preview shows every problematic row but only the first new ones, to keep the page light.
PREVIEW_NEW_ROWS_LIMIT = 200


@router.get("", response_class=HTMLResponse)
def upload_page(request: Request) -> HTMLResponse:
    return _render_upload(request)


@router.post("", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    db: DbSession,
    file: Annotated[UploadFile, File()],
    file_format: Annotated[str, Form(alias="format")] = "csv",
) -> HTMLResponse:
    try:
        content = await read_upload(file)
        preview = preview_import(db, content, get_importer(file_format))
    except ImportFileError as exc:
        return _render_upload(request, error=exc.message)

    token = upload_store.save_upload(content, file_format) if preview.new_rows else None
    problems = [row for row in preview.rows if row.status is not RowStatus.NEW]
    shown_new = preview.new_rows[:PREVIEW_NEW_ROWS_LIMIT]
    return templates.TemplateResponse(
        request,
        "imports/preview.html",
        {
            "active_page": "import",
            "filename": file.filename,
            "token": token,
            "counts": {status: preview.count(status) for status in RowStatus},
            "rows": sorted(problems + shown_new, key=lambda row: row.line),
            "hidden_new": len(preview.new_rows) - len(shown_new),
        },
    )


@router.post("/{token}/confirm", response_class=HTMLResponse)
def confirm_import(
    request: Request, token: str, db: DbSession, providers: RateProviders
) -> HTMLResponse:
    content, file_format = upload_store.load_upload(token)
    report = run_import(db, content, get_importer(file_format), providers)
    upload_store.delete_upload(token)
    return templates.TemplateResponse(
        request, "imports/result.html", {"active_page": "import", "report": report}
    )


@router.post("/{token}/cancel")
def cancel_import(token: str) -> Response:
    upload_store.delete_upload(token)
    return RedirectResponse("/import", status_code=status.HTTP_303_SEE_OTHER)


def _render_upload(request: Request, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "imports/upload.html",
        {"active_page": "import", "importers": IMPORTERS.values(), "error": error},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if error else status.HTTP_200_OK,
    )
