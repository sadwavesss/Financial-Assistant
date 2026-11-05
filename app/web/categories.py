"""HTML page for the knowledge base: categories and their keywords."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from app.dependencies import DbSession
from app.models import TransactionType
from app.schemas.category import CategoryIn, CategoryUpdate
from app.services import categories as service
from app.services.errors import InvalidDataError
from app.utils.validation import humanize_errors
from app.web.templating import templates

router = APIRouter()

MESSAGES = {
    "created": "Категория создана.",
    "updated": "Категория сохранена.",
    "deleted": "Категория удалена.",
    "rule_added": "Ключевое слово добавлено.",
    "rule_deleted": "Ключевое слово удалено.",
}
TextField = Annotated[str, Form()]


@router.get("/categories", response_class=HTMLResponse)
def categories_page(request: Request, db: DbSession) -> HTMLResponse:
    return _render(request, db, message=MESSAGES.get(request.query_params.get("message", "")))


@router.post("/categories")
def create_category(
    request: Request, db: DbSession, name: TextField, type: TextField, color: TextField
) -> Response:
    return _run(
        request,
        db,
        lambda: service.create_category(
            db, CategoryIn.model_validate({"name": name, "type": type, "color": color})
        ),
        "created",
    )


@router.post("/categories/{category_id}/edit")
def update_category(
    request: Request, category_id: int, db: DbSession, name: TextField, color: TextField
) -> Response:
    return _run(
        request,
        db,
        lambda: service.update_category(
            db, category_id, CategoryUpdate.model_validate({"name": name, "color": color})
        ),
        "updated",
    )


@router.post("/categories/{category_id}/delete")
def delete_category(request: Request, category_id: int, db: DbSession) -> Response:
    return _run(request, db, lambda: service.delete_category(db, category_id), "deleted")


@router.post("/categories/{category_id}/rules")
def add_rule(request: Request, category_id: int, db: DbSession, keyword: TextField) -> Response:
    return _run(request, db, lambda: service.add_rule(db, category_id, keyword), "rule_added")


@router.post("/rules/{rule_id}/delete")
def delete_rule(request: Request, rule_id: int, db: DbSession) -> Response:
    return _run(request, db, lambda: service.delete_rule(db, rule_id), "rule_deleted")


def _run(request: Request, db: DbSession, action: Callable[[], object], message: str) -> Response:
    """Run the change and redirect back, or show the page with the error."""
    try:
        action()
    except ValidationError as exc:
        return _render(request, db, error="; ".join(humanize_errors(exc).values()))
    except InvalidDataError as exc:
        return _render(request, db, error=exc.message)
    return RedirectResponse(f"/categories?message={message}", status_code=status.HTTP_303_SEE_OTHER)


def _render(
    request: Request, db: DbSession, message: str | None = None, error: str | None = None
) -> HTMLResponse:
    categories = service.list_categories(db)
    return templates.TemplateResponse(
        request,
        "categories/list.html",
        {
            "active_page": "categories",
            "groups": [
                (kind, [c for c in categories if c.type is kind]) for kind in TransactionType
            ],
            "counts": service.transaction_counts(db),
            "message": message,
            "error": error,
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if error else status.HTTP_200_OK,
    )
