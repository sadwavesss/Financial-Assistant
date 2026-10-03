"""REST API for transactions."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import DbSession, RateProviders
from app.schemas.transaction import (
    TransactionFilters,
    TransactionIn,
    TransactionOut,
    TransactionPage,
)
from app.services import transactions as service

router = APIRouter(prefix="/transactions", tags=["Операции"])


@router.get("", response_model=TransactionPage, summary="Список операций с фильтрами")
def list_transactions(db: DbSession, filters: Annotated[TransactionFilters, Query()]):
    result = service.list_transactions(db, filters)
    return TransactionPage(
        items=[TransactionOut.model_validate(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
        income_byn=result.income_byn,
        expense_byn=result.expense_byn,
    )


@router.post(
    "",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить операцию",
)
def create_transaction(data: TransactionIn, db: DbSession, providers: RateProviders):
    return service.create_transaction(db, data, providers)


@router.get("/{transaction_id}", response_model=TransactionOut, summary="Получить операцию")
def get_transaction(transaction_id: int, db: DbSession):
    return service.get_transaction(db, transaction_id)


@router.put("/{transaction_id}", response_model=TransactionOut, summary="Изменить операцию")
def update_transaction(
    transaction_id: int, data: TransactionIn, db: DbSession, providers: RateProviders
):
    return service.update_transaction(db, transaction_id, data, providers)


@router.delete(
    "/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить операцию"
)
def delete_transaction(transaction_id: int, db: DbSession) -> None:
    service.delete_transaction(db, transaction_id)
