"""REST API of the hybrid categorizer: try a description, train, re-categorize, evaluate."""

from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.categorization import (
    CategorizeIn,
    DecisionOut,
    ModelStatusOut,
    RecategorizationOut,
)
from app.services import categorization as service
from app.services.categorization_eval import evaluate, load_last_report

router = APIRouter(prefix="/categorization", tags=["Категоризация"])


@router.post(
    "/predict",
    response_model=DecisionOut,
    summary="Определить категорию по описанию",
    description=(
        "Ничего не сохраняет. Возвращает решение и пошаговый протокол: правила → модель → арбитр."
    ),
)
def predict(data: CategorizeIn, db: DbSession) -> DecisionOut:
    decision = service.HybridCategorizer.from_db(db).categorize(data.description, data.type)
    arbiter = decision.trace["steps"][-1]
    return DecisionOut(
        category_id=decision.category_id,
        category=arbiter["category"],
        source=decision.source,
        confidence=decision.confidence,
        needs_review=decision.needs_review,
        decision=decision.kind.value,
        reason=arbiter["reason"],
        trace=decision.trace,
    )


@router.get("/status", response_model=ModelStatusOut, summary="Состояние модели")
def status(db: DbSession) -> ModelStatusOut:
    return _status_out(service.model_status(db))


@router.post("/train", response_model=ModelStatusOut, summary="Обучить модель заново")
def train(db: DbSession) -> ModelStatusOut:
    service.train_classifier(db)
    return _status_out(service.model_status(db))


@router.post(
    "/recategorize",
    response_model=RecategorizationOut,
    summary="Перекатегоризировать операции без ручной категории",
)
def recategorize(db: DbSession) -> RecategorizationOut:
    report = service.recategorize_all(db)
    return RecategorizationOut(
        processed=report.processed, changed=report.changed, needs_review=report.needs_review
    )


@router.post("/evaluate", summary="Сравнить: только правила / только ML / гибрид")
def run_evaluation(db: DbSession) -> dict:
    return evaluate(db).to_dict()


@router.get("/evaluation", summary="Результаты последней оценки")
def last_evaluation() -> dict | None:
    return load_last_report()


def _status_out(state: service.ModelStatus) -> ModelStatusOut:
    info = state.classifier.info if state.classifier else None
    return ModelStatusOut(
        trained=info is not None,
        trained_at=info.trained_at if info else None,
        samples=info.samples if info else None,
        classes=info.classes if info else None,
        available_samples=state.available_samples,
        needs_review=state.needs_review,
    )
