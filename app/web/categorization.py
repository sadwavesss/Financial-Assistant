"""HTML page of the hybrid categorizer: model status, training, re-categorization, evaluation."""

from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dependencies import DbSession
from app.models import TransactionType
from app.services import categorization as service
from app.services.categorization_eval import (
    SCENARIO_LABELS,
    VARIANT_LABELS,
    evaluate,
    load_last_report,
)
from app.services.errors import InvalidDataError
from app.web.templating import templates

router = APIRouter(prefix="/categorization")


@router.get("", response_class=HTMLResponse)
def categorization_page(
    request: Request,
    db: DbSession,
    description: Annotated[str, Query(max_length=255)] = "",
    transaction_type: Annotated[TransactionType, Query(alias="type")] = TransactionType.EXPENSE,
) -> HTMLResponse:
    decision = (
        service.HybridCategorizer.from_db(db).categorize(description, transaction_type)
        if description.strip()
        else None
    )
    params = request.query_params
    return templates.TemplateResponse(
        request,
        "categorization/index.html",
        {
            "active_page": "categorization",
            "status": service.model_status(db),
            "report": load_last_report(),
            "scenario_labels": SCENARIO_LABELS,
            "variant_labels": VARIANT_LABELS,
            "description": description,
            "selected_type": transaction_type.value,
            "decision": decision,
            "message": params.get("message"),
            "error": params.get("error"),
        },
    )


@router.post("/train")
def train(db: DbSession) -> RedirectResponse:
    try:
        info = service.train_classifier(db).info
    except InvalidDataError as exc:
        return _back(error=exc.message)
    return _back(message=f"Модель обучена на {info.samples} операциях ({info.classes} категорий).")


@router.post("/recategorize")
def recategorize(db: DbSession) -> RedirectResponse:
    report = service.recategorize_all(db)
    return _back(
        message=(
            f"Обработано операций: {report.processed}, категория изменилась у {report.changed}, "
            f"требуют проверки: {report.needs_review}."
        )
    )


@router.post("/evaluate")
def run_evaluation(db: DbSession) -> RedirectResponse:
    try:
        evaluate(db)
    except InvalidDataError as exc:
        return _back(error=exc.message)
    return _back(message="Оценка качества выполнена.")


def _back(**params: str) -> RedirectResponse:
    return RedirectResponse(
        f"/categorization?{urlencode(params)}", status_code=status.HTTP_303_SEE_OTHER
    )
