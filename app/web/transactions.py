"""HTML pages for transactions: list with filters, create/edit form, delete."""

import datetime as dt
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from app.dependencies import DbSession, RateProviders
from app.models import Currency, Transaction, TransactionType
from app.schemas.transaction import RateMode, TransactionFilters, TransactionIn
from app.services import transactions as service
from app.services.categories import list_categories
from app.services.categorization import model_status
from app.services.errors import InvalidDataError
from app.services.exchange_rates import RateQuote, RateUnavailableError
from app.utils.validation import humanize_errors
from app.web.forms import clean_form
from app.web.templating import templates

router = APIRouter(prefix="/transactions")

MESSAGES = {
    "created": "Операция добавлена.",
    "updated": "Операция сохранена.",
    "deleted": "Операция удалена.",
}


@router.get("", response_class=HTMLResponse)
def transaction_list(request: Request, db: DbSession) -> HTMLResponse:
    raw_filters = clean_form(request.query_params)
    try:
        filters = TransactionFilters.model_validate(raw_filters)
        errors: dict[str, str] = {}
    except ValidationError as exc:
        filters, errors = TransactionFilters(), humanize_errors(exc)

    result = service.list_transactions(db, filters)
    # Query string without page/message, used to build pagination links that keep filters.
    filter_query = urlencode({k: v for k, v in raw_filters.items() if k not in ("page", "message")})
    return templates.TemplateResponse(
        request,
        "transactions/list.html",
        {
            "active_page": "transactions",
            "result": result,
            "filters": raw_filters,
            "errors": errors,
            "filter_query": filter_query,
            "categories": list_categories(db),
            "review_count": model_status(db).needs_review,
            "message": MESSAGES.get(request.query_params.get("message", "")),
        },
    )


@router.get("/new", response_class=HTMLResponse)
def new_transaction_form(request: Request, db: DbSession) -> HTMLResponse:
    form = {"date": dt.date.today().isoformat(), "type": "expense", "currency": "BYN"}
    return _render_form(request, db, form=form)


@router.post("/new", response_class=HTMLResponse)
async def create_transaction(request: Request, db: DbSession, providers: RateProviders) -> Response:
    form = clean_form(await request.form())
    return _save(request, db, form, lambda data: service.create_transaction(db, data, providers))


@router.get("/{transaction_id}/edit", response_class=HTMLResponse)
def edit_transaction_form(request: Request, transaction_id: int, db: DbSession) -> HTMLResponse:
    transaction = service.get_transaction(db, transaction_id)
    form = {
        "date": transaction.date.isoformat(),
        "type": transaction.type.value,
        "amount": str(transaction.amount),
        "currency": transaction.currency.value,
        "description": transaction.description,
        "category_id": str(transaction.category_id or ""),
    }
    return _render_form(request, db, form=form, transaction=transaction)


@router.post("/{transaction_id}/edit", response_class=HTMLResponse)
async def update_transaction(
    request: Request, transaction_id: int, db: DbSession, providers: RateProviders
) -> Response:
    transaction = service.get_transaction(db, transaction_id)
    form = clean_form(await request.form())
    return _save(
        request,
        db,
        form,
        lambda data: service.update_transaction(db, transaction_id, data, providers),
        transaction=transaction,
    )


@router.post("/{transaction_id}/delete")
def delete_transaction(transaction_id: int, db: DbSession) -> RedirectResponse:
    service.delete_transaction(db, transaction_id)
    return _redirect_to_list("deleted")


def _save(
    request: Request,
    db: DbSession,
    form: dict[str, str],
    action: Callable[[TransactionIn], Transaction],
    transaction: Transaction | None = None,
) -> Response:
    """Validate the form, run create/update and redirect, or re-render the form with errors."""
    try:
        action(TransactionIn.model_validate(form))
    except ValidationError as exc:
        return _render_form(request, db, form, transaction, errors=humanize_errors(exc))
    except InvalidDataError as exc:
        errors = {exc.field or "__all__": exc.message}
        return _render_form(request, db, form, transaction, errors=errors)
    except RateUnavailableError as exc:
        return _render_form(
            request, db, form, transaction, errors={"rate": exc.message}, history=exc.history
        )
    return _redirect_to_list("updated" if transaction else "created")


def _render_form(
    request: Request,
    db: DbSession,
    form: dict[str, Any],
    transaction: Transaction | None = None,
    errors: dict[str, str] | None = None,
    history: RateQuote | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "transactions/form.html",
        {
            "active_page": "transactions" if transaction else "transaction_new",
            "form": form,
            "transaction": transaction,
            "errors": errors or {},
            "history": history,
            "categories": list_categories(db),
            "types": list(TransactionType),
            "currencies": list(Currency),
            "rate_modes": RateMode,
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT if errors else status.HTTP_200_OK,
    )


def _redirect_to_list(message: str) -> RedirectResponse:
    return RedirectResponse(
        f"/transactions?message={message}", status_code=status.HTTP_303_SEE_OTHER
    )
