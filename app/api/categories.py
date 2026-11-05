"""REST API for categories and keyword rules (the categorization knowledge base)."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import DbSession
from app.models import TransactionType
from app.schemas.category import CategoryIn, CategoryOut, CategoryUpdate, RuleIn, RuleOut
from app.services import categories as service

router = APIRouter(tags=["Категории"])


@router.get("/categories", response_model=list[CategoryOut], summary="Список категорий")
def read_categories(
    db: DbSession,
    transaction_type: Annotated[TransactionType | None, Query(alias="type")] = None,
):
    return service.list_categories(db, transaction_type)


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать категорию",
)
def create_category(data: CategoryIn, db: DbSession):
    return service.create_category(db, data)


@router.put("/categories/{category_id}", response_model=CategoryOut, summary="Изменить категорию")
def update_category(category_id: int, data: CategoryUpdate, db: DbSession):
    return service.update_category(db, category_id, data)


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить категорию",
)
def delete_category(category_id: int, db: DbSession) -> None:
    service.delete_category(db, category_id)


@router.post(
    "/categories/{category_id}/rules",
    response_model=RuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить ключевое слово",
)
def add_rule(category_id: int, data: RuleIn, db: DbSession):
    return service.add_rule(db, category_id, data.keyword)


@router.delete(
    "/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить ключевое слово"
)
def delete_rule(rule_id: int, db: DbSession) -> None:
    service.delete_rule(db, rule_id)
