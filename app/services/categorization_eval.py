"""Quality evaluation of categorization: rules only vs model only vs the hybrid.

Ground truth: transactions whose category was set by a person (source "manual").
Two scenarios:
- "random": a random 70/30 split — the usual case, most merchants repeat;
- "new_descriptions": descriptions in the test part never occur in the training part
  (grouped split) — how the system copes with unseen merchants.
In both, the model is trained on the training part only; the three variants share the same
arbiter, so they differ only in which components are enabled.

Metrics: accuracy (correct among all test rows), coverage (share of rows that got a category
other than the "Прочие" fallback), precision on covered rows, macro F1, time per transaction.
"""

import datetime as dt
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sklearn.metrics import f1_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.ml.text_classifier import TextClassifier
from app.models import CategorySource, Transaction, TransactionType
from app.services.categorization import HybridCategorizer
from app.services.errors import InvalidDataError
from app.utils.text import normalize_text

REPORT_FILE = "evaluation.json"
MIN_SAMPLES = 30
SCENARIO_LABELS = {
    "random": "Случайное разбиение 70/30",
    "new_descriptions": "Новые (ранее не встречавшиеся) описания",
}
VARIANT_LABELS = {"rules": "Только правила", "ml": "Только ML", "hybrid": "Гибрид"}


@dataclass(frozen=True)
class VariantMetrics:
    variant: str
    accuracy: float
    coverage: float
    precision_covered: float
    macro_f1: float
    ms_per_item: float


@dataclass(frozen=True)
class ScenarioReport:
    scenario: str
    train_size: int
    test_size: int
    variants: list[VariantMetrics]


@dataclass(frozen=True)
class EvaluationReport:
    created_at: str
    samples: int
    seed: int
    scenarios: list[ScenarioReport]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Sample:
    description: str
    type: TransactionType
    label: int


def evaluate(db: Session, seed: int = 42, test_size: float = 0.3) -> EvaluationReport:
    samples = _labeled_samples(db)
    if len(samples) < MIN_SAMPLES or len({s.label for s in samples}) < 2:
        raise InvalidDataError(
            f"Для оценки нужно не менее {MIN_SAMPLES} операций с категориями, "
            f"проставленными вручную (сейчас {len(samples)})."
        )

    indexes = list(range(len(samples)))
    labels = [s.label for s in samples]
    splits = {"random": _random_split(indexes, labels, test_size, seed)}
    groups = [normalize_text(s.description) for s in samples]
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train, test = next(splitter.split(indexes, labels, groups))
    splits["new_descriptions"] = (list(train), list(test))

    scenarios = []
    for name, (train_idx, test_idx) in splits.items():
        train_set = [samples[i] for i in train_idx]
        test_set = [samples[i] for i in test_idx]
        classifier = TextClassifier.train(
            [s.description for s in train_set], [s.label for s in train_set]
        )
        variants = {
            "rules": HybridCategorizer.from_db(db, use_model=False),
            "ml": HybridCategorizer.from_db(db, use_rules=False, classifier=classifier),
            "hybrid": HybridCategorizer.from_db(db, classifier=classifier),
        }
        scenarios.append(
            ScenarioReport(
                scenario=name,
                train_size=len(train_set),
                test_size=len(test_set),
                variants=[
                    _measure(key, categorizer, test_set) for key, categorizer in variants.items()
                ],
            )
        )

    report = EvaluationReport(
        created_at=dt.datetime.now().isoformat(timespec="seconds"),
        samples=len(samples),
        seed=seed,
        scenarios=scenarios,
    )
    _save(report, config.MODELS_DIR)
    return report


def load_last_report() -> dict | None:
    path = config.MODELS_DIR / REPORT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _labeled_samples(db: Session) -> list[_Sample]:
    rows = db.execute(
        select(Transaction.description, Transaction.type, Transaction.category_id).where(
            Transaction.category_source == CategorySource.MANUAL,
            Transaction.category_id.is_not(None),
            Transaction.description != "",
        )
    ).all()
    return [_Sample(*row) for row in rows]


def _random_split(
    indexes: list[int], labels: list[int], test_size: float, seed: int
) -> tuple[list[int], list[int]]:
    # Stratify when every category has at least two examples, otherwise split plainly.
    counts = {label: labels.count(label) for label in set(labels)}
    stratify = labels if min(counts.values()) >= 2 else None
    train, test = train_test_split(
        indexes, test_size=test_size, random_state=seed, stratify=stratify
    )
    return list(train), list(test)


def _measure(name: str, categorizer: HybridCategorizer, test_set: list[_Sample]) -> VariantMetrics:
    started = time.perf_counter()
    decisions = categorizer.categorize_many([(s.description, s.type) for s in test_set])
    elapsed_ms = (time.perf_counter() - started) * 1000

    y_true = [s.label for s in test_set]
    y_pred = [d.category_id if d.category_id is not None else -1 for d in decisions]
    covered = [d.source is not CategorySource.FALLBACK for d in decisions]
    correct = [t == p for t, p in zip(y_true, y_pred, strict=True)]
    covered_correct = [c for c, cov in zip(correct, covered, strict=True) if cov]
    return VariantMetrics(
        variant=name,
        accuracy=round(sum(correct) / len(test_set), 4),
        coverage=round(sum(covered) / len(test_set), 4),
        precision_covered=round(sum(covered_correct) / len(covered_correct), 4)
        if covered_correct
        else 0.0,
        macro_f1=round(float(f1_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        ms_per_item=round(elapsed_ms / len(test_set), 3),
    )


def _save(report: EvaluationReport, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / REPORT_FILE).write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
