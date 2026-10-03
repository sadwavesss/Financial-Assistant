"""REST API for categories."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import DbSession
from app.models import TransactionType
from app.schemas.category import CategoryOut
from app.services.categories import list_categories

router = APIRouter(prefix="/categories", tags=["Категории"])


@router.get("", response_model=list[CategoryOut], summary="Список категорий")
def read_categories(
    db: DbSession,
    transaction_type: Annotated[TransactionType | None, Query(alias="type")] = None,
):
    return list_categories(db, transaction_type)
