"""Statistical forecasting of a time series of expenses (one value per week or month).

Three models of increasing complexity compete:
- moving average of the last values (baseline: "spend as usual");
- linear regression on the time index (captures a steady trend);
- Holt's exponential smoothing with a damped trend (adapts to recent level and trend).

The model is chosen by a rolling-origin backtest: for each of the last `test_points` values
every model is fitted only on the values before it and predicts it one step ahead; the
smallest mean absolute error (MAE) wins. The spread of the backtest errors gives an
approximate 80 % prediction interval that widens with the horizon.
"""

import math
import statistics
import warnings
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LinearRegression
from statsmodels.tsa.holtwinters import Holt

Z_80 = 1.2816  # standard normal quantile for a two-sided 80 % interval
MIN_TRAIN_POINTS = 4
MIN_TEST_POINTS = 2


class InsufficientHistoryError(ValueError):
    """The series is too short to compare models honestly."""


class Forecaster(ABC):
    name: str
    label: str

    @abstractmethod
    def predict(self, history: Sequence[float], horizon: int) -> list[float]:
        """Fit on `history` and return `horizon` future values (never negative)."""


class MovingAverage(Forecaster):
    name, label = "moving_average", "Скользящее среднее (3)"

    def __init__(self, window: int = 3) -> None:
        self.window = window

    def predict(self, history: Sequence[float], horizon: int) -> list[float]:
        value = statistics.fmean(history[-self.window :])
        return [max(0.0, value)] * horizon


class LinearTrend(Forecaster):
    name, label = "linear_regression", "Линейная регрессия"

    def predict(self, history: Sequence[float], horizon: int) -> list[float]:
        x = np.arange(len(history)).reshape(-1, 1)
        model = LinearRegression().fit(x, np.asarray(history, dtype=float))
        future = np.arange(len(history), len(history) + horizon).reshape(-1, 1)
        return [max(0.0, float(v)) for v in model.predict(future)]


class HoltSmoothing(Forecaster):
    name, label = "holt", "Сглаживание Хольта"

    def predict(self, history: Sequence[float], horizon: int) -> list[float]:
        series = np.asarray(history, dtype=float)
        if np.allclose(series, series[0]):  # a flat series breaks the optimizer; it is trivial
            return [max(0.0, float(series[0]))] * horizon
        with warnings.catch_warnings():
            # Short series make statsmodels warn about convergence; the result is still usable.
            warnings.simplefilter("ignore")
            fitted = Holt(series, damped_trend=True, initialization_method="estimated").fit()
            values = fitted.forecast(horizon)
        return [max(0.0, float(v)) if math.isfinite(v) else 0.0 for v in values]


MODELS: tuple[Forecaster, ...] = (MovingAverage(), LinearTrend(), HoltSmoothing())


@dataclass(frozen=True)
class ModelScore:
    name: str
    label: str
    mae: float
    mape: float | None  # mean absolute percentage error; None if all actual values are zero
    errors: tuple[float, ...]  # actual - predicted for every backtest point


@dataclass(frozen=True)
class ForecastPoint:
    value: float
    lower: float
    upper: float


@dataclass(frozen=True)
class ForecastResult:
    best: ModelScore
    scores: list[ModelScore]  # all models, best first
    points: list[ForecastPoint]
    test_points: int


def backtest(model: Forecaster, series: Sequence[float], test_points: int) -> ModelScore:
    actual, errors = [], []
    for index in range(len(series) - test_points, len(series)):
        predicted = model.predict(series[:index], 1)[0]
        actual.append(series[index])
        errors.append(series[index] - predicted)
    nonzero = [(abs(e), a) for e, a in zip(errors, actual, strict=True) if a > 0]
    return ModelScore(
        name=model.name,
        label=model.label,
        mae=statistics.fmean(abs(e) for e in errors),
        mape=statistics.fmean(e / a for e, a in nonzero) if nonzero else None,
        errors=tuple(errors),
    )


def forecast(
    series: Sequence[float],
    horizon: int,
    max_test_points: int = 6,
    models: Sequence[Forecaster] = MODELS,
) -> ForecastResult:
    """Choose the best model by backtest MAE and forecast `horizon` steps with intervals."""
    test_points = min(max_test_points, len(series) - MIN_TRAIN_POINTS)
    if test_points < MIN_TEST_POINTS:
        raise InsufficientHistoryError(
            f"Need at least {MIN_TRAIN_POINTS + MIN_TEST_POINTS} values, got {len(series)}"
        )
    # Ties are resolved in favour of the simpler model (models are ordered by complexity).
    scores = sorted((backtest(model, series, test_points) for model in models), key=lambda s: s.mae)
    best = scores[0]
    model = next(m for m in models if m.name == best.name)
    values = model.predict(series, horizon)

    # Residual spread; the interval grows like sqrt(step), as for a random walk of errors.
    spread = statistics.pstdev(best.errors) if len(best.errors) > 1 else best.mae
    points = []
    for step, value in enumerate(values, start=1):
        margin = Z_80 * spread * math.sqrt(step)
        points.append(ForecastPoint(value, max(0.0, value - margin), value + margin))
    return ForecastResult(best, scores, points, test_points)
