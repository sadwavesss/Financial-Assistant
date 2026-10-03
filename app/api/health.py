"""Health check: confirms the application is running and the database is reachable."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app import __version__
from app.dependencies import DbSession

router = APIRouter(tags=["Служебное"])


class HealthResponse(BaseModel):
    status: str
    version: str


@router.get("/health", response_model=HealthResponse, summary="Проверка работоспособности")
def health(db: DbSession) -> HealthResponse:
    db.execute(text("SELECT 1"))
    return HealthResponse(status="ok", version=__version__)
