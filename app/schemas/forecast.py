"""Schemas of the forecast API."""

import datetime as dt

from pydantic import BaseModel

from app.services.analytics import Granularity
from app.services.forecast import ForecastReport


class HistoryPointOut(BaseModel):
    start: dt.date
    label: str
    value: float


class ForecastPointOut(HistoryPointOut):
    lower: float
    upper: float


class ModelScoreOut(BaseModel):
    name: str
    label: str
    mae: float
    mape: float | None
    selected: bool


class CategoryForecastOut(BaseModel):
    category_id: int | None
    name: str
    next_value: float
    total: float
    recent_average: float
    change: float | None
    model: str


class ForecastOut(BaseModel):
    granularity: Granularity
    horizon: int
    test_points: int
    data_gap: bool
    total: float
    current_spent: float
    current_elapsed: float
    history: list[HistoryPointOut]
    forecast: list[ForecastPointOut]
    models: list[ModelScoreOut]
    categories: list[CategoryForecastOut]

    @classmethod
    def from_report(cls, report: ForecastReport) -> "ForecastOut":
        best = report.result.best.name
        return cls(
            granularity=report.granularity,
            horizon=report.horizon,
            test_points=report.result.test_points,
            data_gap=report.data_gap,
            total=round(report.total, 2),
            current_spent=round(report.current_spent, 2),
            current_elapsed=round(report.current_elapsed, 3),
            history=[
                HistoryPointOut(start=p.start, label=p.label, value=p.value) for p in report.history
            ],
            forecast=[
                ForecastPointOut(
                    start=p.start,
                    label=p.label,
                    value=round(p.value, 2),
                    lower=round(p.lower, 2),
                    upper=round(p.upper, 2),
                )
                for p in report.points
            ],
            models=[
                ModelScoreOut(
                    name=s.name,
                    label=s.label,
                    mae=round(s.mae, 2),
                    mape=s.mape,
                    selected=s.name == best,
                )
                for s in report.result.scores
            ],
            categories=[
                CategoryForecastOut(
                    category_id=c.category_id,
                    name=c.name,
                    next_value=round(c.next_value, 2),
                    total=round(c.total, 2),
                    recent_average=round(c.recent_average, 2),
                    change=c.change,
                    model=c.model,
                )
                for c in report.categories
            ],
        )
