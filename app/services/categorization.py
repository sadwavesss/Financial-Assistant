"""Hybrid categorization: keyword knowledge base + text classifier + arbitration.

Cascade for one transaction (description, type):
1. Rules (symbolic): candidate categories whose keywords occur in the description.
2. Classifier (statistical): the most probable category of the same type and its probability.
3. Arbiter:
   - rule and model agree                    -> the rule's category;
   - several rules match, model picks one    -> the candidate chosen by the model;
   - rule and a confident model disagree     -> the rule's category, marked for review (conflict);
   - rule only (no model or a weak one)      -> the rule's category;
   - no rule, confident model                -> the model's category;
   - no rule, unsure model or no model       -> the system category "Прочие ...", for review.
Every decision carries a step-by-step trace (what each component returned and why the arbiter
chose the result); it is stored with the transaction and shown to the user.
Manual categories are never changed automatically.
"""

import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config
from app.config import get_settings
from app.ml.text_classifier import MODEL_FILE, Prediction, TextClassifier
from app.models import Category, CategoryRule, CategorySource, Transaction, TransactionType
from app.services.errors import InvalidDataError
from app.services.rule_matcher import KeywordRule, RuleCandidate, RuleMatcher

TRACE_VERSION = 1
MIN_TRAINING_SAMPLES = 10


class DecisionKind(StrEnum):
    RULE_AND_ML_AGREE = "rule_and_ml_agree"
    RULES_RESOLVED_BY_ML = "rules_resolved_by_ml"
    CONFLICT = "conflict"
    RULE_ONLY = "rule_only"
    ML = "ml"
    LOW_CONFIDENCE = "low_confidence"
    NO_INFORMATION = "no_information"


REASONS = {
    DecisionKind.RULE_AND_ML_AGREE: "Правило и модель указали одну и ту же категорию.",
    DecisionKind.RULES_RESOLVED_BY_ML: (
        "Сработали правила нескольких категорий; выбрана та, которую поддержала модель."
    ),
    DecisionKind.CONFLICT: (
        "Правило и уверенная модель разошлись. Приоритет у базы знаний, "
        "но операцию стоит проверить."
    ),
    DecisionKind.RULE_ONLY: "Категория определена по правилу базы знаний.",
    DecisionKind.ML: (
        "Правила не сработали; категория определена моделью с достаточной уверенностью."
    ),
    DecisionKind.LOW_CONFIDENCE: (
        "Правила не сработали, модель не уверена — выбрана категория «Прочие», нужна проверка."
    ),
    DecisionKind.NO_INFORMATION: (
        "Нет ни подходящих правил, ни обученной модели — выбрана категория «Прочие», "
        "нужна проверка."
    ),
}


@dataclass(frozen=True)
class CategoryInfo:
    id: int
    name: str
    type: TransactionType
    is_system: bool


@dataclass(frozen=True)
class Decision:
    category_id: int | None
    source: CategorySource
    confidence: float | None  # model's probability of the chosen category, if known
    needs_review: bool
    kind: DecisionKind
    trace: dict[str, Any] = field(compare=False)


class HybridCategorizer:
    def __init__(
        self,
        categories: Iterable[CategoryInfo],
        matcher: RuleMatcher,
        classifier: TextClassifier | None,
        min_confidence: float,
        conflict_confidence: float,
    ) -> None:
        self.categories = {category.id: category for category in categories}
        self.matcher = matcher
        self.classifier = classifier
        self.min_confidence = min_confidence
        self.conflict_confidence = conflict_confidence
        self._ids_by_type = {
            kind: {c.id for c in self.categories.values() if c.type is kind}
            for kind in TransactionType
        }
        self._fallback = {
            c.type: c.id for c in self.categories.values() if c.is_system
        }  # "Прочие расходы" / "Прочие доходы"

    @classmethod
    def from_db(
        cls,
        db: Session,
        *,
        use_rules: bool = True,
        use_model: bool = True,
        classifier: TextClassifier | None = None,
    ) -> "HybridCategorizer":
        """Build from the current knowledge base.

        The model is the given `classifier` or, if none is given, the saved one; with
        `use_model=False` (or `use_rules=False`) a component is switched off, which is how the
        "rules only" and "model only" variants are evaluated.
        """
        if not use_model:
            model = None
        else:
            model = classifier if classifier is not None else load_classifier()
        settings = get_settings()
        categories = [
            CategoryInfo(c.id, c.name, c.type, c.is_system) for c in db.scalars(select(Category))
        ]
        types = {category.id: category.type for category in categories}
        rules = (
            [
                KeywordRule(rule.keyword, rule.category_id, types[rule.category_id])
                for rule in db.scalars(select(CategoryRule))
            ]
            if use_rules
            else []
        )
        return cls(
            categories,
            RuleMatcher(rules),
            model,
            settings.ml_min_confidence,
            settings.ml_conflict_confidence,
        )

    def categorize(self, description: str, transaction_type: TransactionType) -> Decision:
        return self.categorize_many([(description, transaction_type)])[0]

    def categorize_many(self, items: Sequence[tuple[str, TransactionType]]) -> list[Decision]:
        """Batch version: the classifier is called once for all items (much faster on import)."""
        predictions: list[Prediction | None] = [None] * len(items)
        if self.classifier is not None and items:
            predictions = self.classifier.predict(
                [description for description, _ in items],
                [self._ids_by_type[kind] for _, kind in items],
            )
        return [
            self._arbitrate(description, kind, self.matcher.match(description, kind), prediction)
            for (description, kind), prediction in zip(items, predictions, strict=True)
        ]

    def _arbitrate(
        self,
        description: str,
        transaction_type: TransactionType,
        rules: list[RuleCandidate],
        ml: Prediction | None,
    ) -> Decision:
        rule_ids = [candidate.category_id for candidate in rules]
        if rules and ml and ml.label in rule_ids:
            kind = (
                DecisionKind.RULE_AND_ML_AGREE
                if len(rules) == 1
                else DecisionKind.RULES_RESOLVED_BY_ML
            )
            category_id, source, review = ml.label, CategorySource.RULE, False
        elif rules:
            conflict = ml is not None and ml.confidence >= self.conflict_confidence
            kind = DecisionKind.CONFLICT if conflict else DecisionKind.RULE_ONLY
            category_id, source, review = rule_ids[0], CategorySource.RULE, conflict
        elif ml and ml.confidence >= self.min_confidence:
            kind, category_id, source, review = DecisionKind.ML, ml.label, CategorySource.ML, False
        else:
            kind = DecisionKind.LOW_CONFIDENCE if ml else DecisionKind.NO_INFORMATION
            category_id = self._fallback.get(transaction_type)
            source, review = CategorySource.FALLBACK, True

        confidence = dict(ml.alternatives).get(category_id) if ml else None
        trace = self._trace(description, transaction_type, rules, ml, kind, category_id)
        return Decision(category_id, source, confidence, review, kind, trace)

    def _trace(
        self,
        description: str,
        transaction_type: TransactionType,
        rules: list[RuleCandidate],
        ml: Prediction | None,
        kind: DecisionKind,
        category_id: int | None,
    ) -> dict[str, Any]:
        ml_step: dict[str, Any] = {"component": "ml", "result": None}
        if self.classifier is None:
            ml_step["note"] = "модель не обучена"
        elif ml is not None:
            ml_step["result"] = {
                "category_id": ml.label,
                "category": self._name(ml.label),
                "confidence": ml.confidence,
                "alternatives": [
                    {"category": self._name(label), "confidence": probability}
                    for label, probability in ml.alternatives
                ],
            }
        return {
            "version": TRACE_VERSION,
            "input": {"description": description, "type": transaction_type.value},
            "steps": [
                {
                    "component": "rules",
                    "result": [
                        {
                            "category_id": c.category_id,
                            "category": self._name(c.category_id),
                            "keyword": c.keyword,
                        }
                        for c in rules
                    ],
                },
                ml_step,
                {
                    "component": "arbiter",
                    "decision": kind.value,
                    "category_id": category_id,
                    "category": self._name(category_id),
                    "reason": REASONS[kind],
                },
            ],
            "thresholds": {
                "ml_min_confidence": self.min_confidence,
                "ml_conflict_confidence": self.conflict_confidence,
            },
        }

    def _name(self, category_id: int | None) -> str | None:
        category = self.categories.get(category_id) if category_id is not None else None
        return category.name if category else None


# ---------- Applying decisions to transactions ----------


def apply_decision(transaction: Transaction, decision: Decision) -> None:
    transaction.category_id = decision.category_id
    transaction.category_source = decision.source
    transaction.category_confidence = decision.confidence
    transaction.needs_review = decision.needs_review
    transaction.categorization_trace = decision.trace


def mark_manual(transaction: Transaction, category_id: int | None) -> None:
    """A category chosen by the user: the strongest label, used for training."""
    transaction.category_id = category_id
    transaction.category_source = CategorySource.MANUAL if category_id else None
    transaction.category_confidence = None
    transaction.needs_review = False
    transaction.categorization_trace = None


def categorize_transactions(
    categorizer: HybridCategorizer, transactions: Sequence[Transaction]
) -> None:
    """Assign automatic categories to the given transactions (manual ones are skipped)."""
    pending = [t for t in transactions if t.category_source is not CategorySource.MANUAL]
    decisions = categorizer.categorize_many([(t.description, t.type) for t in pending])
    for transaction, decision in zip(pending, decisions, strict=True):
        apply_decision(transaction, decision)


@dataclass(frozen=True)
class RecategorizationReport:
    processed: int
    changed: int
    needs_review: int


def recategorize_all(db: Session) -> RecategorizationReport:
    """Re-run the hybrid categorizer on every transaction without a manual category."""
    transactions = list(
        db.scalars(
            select(Transaction).where(
                (Transaction.category_source != CategorySource.MANUAL)
                | Transaction.category_source.is_(None)
            )
        )
    )
    before = {t.id: t.category_id for t in transactions}
    categorize_transactions(HybridCategorizer.from_db(db), transactions)
    db.commit()
    return RecategorizationReport(
        processed=len(transactions),
        changed=sum(1 for t in transactions if t.category_id != before[t.id]),
        needs_review=sum(1 for t in transactions if t.needs_review),
    )


@dataclass(frozen=True)
class ModelStatus:
    classifier: TextClassifier | None
    available_samples: int
    needs_review: int


def model_status(db: Session) -> ModelStatus:
    texts, _ = training_data(db)
    review = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.needs_review)
    )
    return ModelStatus(load_classifier(), len(texts), review or 0)


# ---------- Training and the saved model ----------


def training_data(db: Session) -> tuple[list[str], list[int]]:
    """Labels set by the user or by an undisputed rule; the model's own guesses are excluded,
    so the model never learns from its own mistakes."""
    rows = db.execute(
        select(Transaction.description, Transaction.category_id).where(
            Transaction.category_id.is_not(None),
            Transaction.description != "",
            (Transaction.category_source == CategorySource.MANUAL)
            | ((Transaction.category_source == CategorySource.RULE) & ~Transaction.needs_review),
        )
    ).all()
    return [row[0] for row in rows], [row[1] for row in rows]


def train_classifier(db: Session) -> TextClassifier:
    texts, labels = training_data(db)
    if len(texts) < MIN_TRAINING_SAMPLES or len(set(labels)) < 2:
        raise InvalidDataError(
            f"Недостаточно размеченных операций для обучения: нужно не менее "
            f"{MIN_TRAINING_SAMPLES} операций минимум двух категорий (сейчас {len(texts)})."
        )
    classifier = TextClassifier.train(texts, labels)
    classifier.save(config.MODELS_DIR)
    _model_cache.clear()
    return classifier


class _ModelCache:
    """Keeps the loaded model in memory and reloads it only when the file changes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: tuple[Path, float] | None = None
        self._model: TextClassifier | None = None

    def get(self, directory: Path) -> TextClassifier | None:
        path = directory / MODEL_FILE
        key = (path, path.stat().st_mtime) if path.is_file() else None
        with self._lock:
            if key != self._key:
                self._model = TextClassifier.load(directory) if key else None
                self._key = key
            return self._model

    def clear(self) -> None:
        with self._lock:
            self._key, self._model = None, None


_model_cache = _ModelCache()


def load_classifier() -> TextClassifier | None:
    return _model_cache.get(config.MODELS_DIR)
