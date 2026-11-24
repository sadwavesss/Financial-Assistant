"""REST API for budget recommendations."""

from fastapi import APIRouter

from app.dependencies import DbSession
from app.schemas.recommendations import RecommendationsOut
from app.services.recommendations import build_recommendations

router = APIRouter(prefix="/recommendations", tags=["Рекомендации"])


@router.get(
    "",
    response_model=RecommendationsOut,
    summary="Рекомендации по бюджету",
    description=(
        "Факты из аналитики, прогноза (ML) и регулярных платежей обрабатываются машиной вывода "
        "по базе продукционных правил (app/knowledge/recommendation_rules.json). Для каждой "
        "рекомендации возвращаются проверенные условия, а также полный протокол вывода."
    ),
)
def read_recommendations(db: DbSession) -> RecommendationsOut:
    return RecommendationsOut.from_report(build_recommendations(db))
