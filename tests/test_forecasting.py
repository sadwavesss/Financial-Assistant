"""Forecasting: models, backtest-based selection, intervals, series from the database."""

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.importers.csv_importer import CsvImporter
from app.ml.forecasting import (
    HoltSmoothing,
    InsufficientHistoryError,
    LinearTrend,
    MovingAverage,
    backtest,
    forecast,
)
from app.models import Transaction, TransactionType
from app.services.analytics import Granularity
from app.services.demo_data import generate_demo_rows, write_demo_csv
from app.services.errors import InvalidDataError
from app.services.forecast import build_forecast
from app.services.imports import run_import
from app.utils.dates import add_months

TODAY = dt.date(2026, 11, 20)


# ---------- Models ----------


def test_moving_average_uses_the_last_window() -> None:
    assert MovingAverage(3).predict([10, 100, 200, 300], 2) == [200.0, 200.0]


def test_linear_trend_continues_the_line() -> None:
    assert LinearTrend().predict([10, 20, 30, 40], 2) == pytest.approx([50, 60])


def test_holt_follows_a_trend_and_handles_flat_series() -> None:
    trend = HoltSmoothing().predict([100, 110, 120, 130, 140, 150], 1)[0]

    assert 145 < trend < 175
    assert HoltSmoothing().predict([50.0] * 6, 3) == [50.0] * 3


def test_predictions_are_never_negative() -> None:
    falling = [500, 400, 300, 200, 100, 0]

    for model in (MovingAverage(), LinearTrend(), HoltSmoothing()):
        assert min(model.predict(falling, 4)) >= 0


def test_backtest_uses_only_past_values() -> None:
    score = backtest(MovingAverage(1), [1, 2, 3, 4, 5, 6], test_points=2)

    # predicts 5 from [..4] and 6 from [..5] with the previous value: errors of +1
    assert score.errors == (1.0, 1.0)
    assert score.mae == 1.0
    assert score.mape == pytest.approx((1 / 5 + 1 / 6) / 2)


# ---------- Selection ----------


def test_best_model_is_chosen_by_mae() -> None:
    assert forecast([100.0] * 10, 3).best.name == "moving_average"  # tie -> simplest model
    assert forecast([100 + 10 * i for i in range(10)], 3).best.name == "linear_regression"


def test_scores_are_sorted_and_interval_widens() -> None:
    result = forecast([100, 130, 90, 120, 105, 125, 95, 115, 110, 120], 3)

    assert [s.mae for s in result.scores] == sorted(s.mae for s in result.scores)
    widths = [p.upper - p.lower for p in result.points]
    assert widths == sorted(widths) and widths[0] > 0
    assert all(p.lower >= 0 and p.lower <= p.value <= p.upper for p in result.points)


def test_short_series_is_rejected() -> None:
    with pytest.raises(InsufficientHistoryError):
        forecast([1, 2, 3, 4, 5], 1)


# ---------- Service ----------


def add_expense(db: Session, day: dt.date, amount: str) -> None:
    db.add(Transaction(date=day, type=TransactionType.EXPENSE, amount=Decimal(amount),
                       amount_byn=Decimal(amount), description="Покупка"))  # fmt: skip


def test_current_incomplete_month_is_not_training_data(db: Session) -> None:
    for back in range(1, 9):  # eight complete months of 1000 BYN
        add_expense(db, add_months(TODAY.replace(day=10), -back), "1000")
    add_expense(db, TODAY, "50")  # current month: only just started
    db.commit()

    report = build_forecast(db, Granularity.MONTH, 2, today=TODAY)

    assert len(report.history) == 8
    assert [p.start for p in report.points] == [dt.date(2026, 11, 1), dt.date(2026, 12, 1)]
    assert report.points[0].value == pytest.approx(1000)
    assert report.current_spent == 50
    assert report.current_forecast is report.points[0]
    assert not report.data_gap


def test_trailing_periods_without_data_are_treated_as_missing(db: Session) -> None:
    for back in range(3, 11):  # nothing entered in the last two complete months
        add_expense(db, add_months(TODAY.replace(day=10), -back), "800")
    db.commit()

    report = build_forecast(db, Granularity.MONTH, 3, today=TODAY)

    assert report.data_gap
    assert report.history[-1].start == dt.date(2026, 8, 1)
    assert report.points[0].start == dt.date(2026, 9, 1)
    assert report.points[0].value == pytest.approx(800)


def test_empty_months_inside_history_count_as_zero(db: Session) -> None:
    for back in (1, 2, 4, 5, 6, 7):  # month 3 back is empty
        add_expense(db, add_months(TODAY.replace(day=10), -back), "600")
    db.commit()

    report = build_forecast(db, Granularity.MONTH, 1, today=TODAY)

    assert [p.value for p in report.history] == [600, 600, 600, 600, 0, 600, 600]


def test_not_enough_history_and_bad_horizon(db: Session) -> None:
    add_expense(db, TODAY - dt.timedelta(days=40), "100")
    db.commit()

    with pytest.raises(InvalidDataError, match="не менее 6"):
        build_forecast(db, Granularity.MONTH, today=TODAY)
    with pytest.raises(InvalidDataError, match="Горизонт"):
        build_forecast(db, Granularity.MONTH, 7, today=TODAY)
    with pytest.raises(InvalidDataError):
        build_forecast(db, Granularity.DAY, today=TODAY)


def test_demo_data_monthly_and_weekly(seeded_db: Session, providers, tmp_path: Path) -> None:
    path = tmp_path / "demo.csv"
    write_demo_csv(generate_demo_rows(months=12, end=TODAY), path)
    run_import(seeded_db, path.read_bytes(), CsvImporter(), providers)

    monthly = build_forecast(seeded_db, Granularity.MONTH, 3, today=TODAY)
    weekly = build_forecast(seeded_db, Granularity.WEEK, 4, today=TODAY)

    assert len(monthly.points) == 3 and len(weekly.points) == 4
    assert {s.name for s in monthly.result.scores} == {
        "moving_average",
        "linear_regression",
        "holt",
    }
    # Monthly spending of the demo budget is 1.2-3 thousand BYN; the forecast is in that range.
    assert 1000 < monthly.points[0].value < 3500
    assert monthly.result.best.mape < 0.3
    assert monthly.categories[0].name == "Продукты"


def test_api_and_page(client: TestClient, db: Session) -> None:
    for back in range(1, 9):
        add_expense(db, add_months(dt.date.today().replace(day=10), -back), str(900 + 10 * back))
    db.commit()

    body = client.get("/api/forecast", params={"granularity": "month", "horizon": 2}).json()
    page = client.get("/forecast")
    empty_error = client.get("/api/forecast", params={"horizon": 99})

    assert len(body["forecast"]) == 2
    assert sum(m["selected"] for m in body["models"]) == 1
    assert "Сравнение моделей" in page.text and 'id="forecast-data"' in page.text
    assert empty_error.status_code == 422


def test_page_shows_error_without_history(client: TestClient) -> None:
    assert "Для прогноза нужно" in client.get("/forecast").text
