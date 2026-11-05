"""Arbiter of the hybrid categorizer: every branch of the decision logic and the trace."""

from collections.abc import Collection, Sequence

import pytest

from app.ml.text_classifier import Prediction
from app.models import CategorySource, TransactionType
from app.services.categorization import CategoryInfo, DecisionKind, HybridCategorizer
from app.services.rule_matcher import KeywordRule, RuleMatcher

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME
RULE, ML, FALLBACK = CategorySource.RULE, CategorySource.ML, CategorySource.FALLBACK
GROCERIES, CAFE, EDUCATION, OTHER, SALARY, OTHER_INCOME = 1, 2, 3, 4, 5, 6
CATEGORIES = [
    CategoryInfo(GROCERIES, "Продукты", EXPENSE, False),
    CategoryInfo(CAFE, "Кафе", EXPENSE, False),
    CategoryInfo(EDUCATION, "Образование", EXPENSE, False),
    CategoryInfo(OTHER, "Прочие расходы", EXPENSE, True),
    CategoryInfo(SALARY, "Зарплата", INCOME, False),
    CategoryInfo(OTHER_INCOME, "Прочие доходы", INCOME, True),
]
RULES = RuleMatcher(
    [
        KeywordRule("евроопт", GROCERIES, EXPENSE),
        KeywordRule("бгуир", EDUCATION, EXPENSE),
        KeywordRule("столовая", CAFE, EXPENSE),
    ]
)


class FakeClassifier:
    """Returns a fixed (label, confidence) for every description."""

    def __init__(self, answers: dict[str, tuple[int, float]]) -> None:
        self.answers = answers

    def predict(
        self, texts: Sequence[str], allowed: Sequence[Collection[int]]
    ) -> list[Prediction | None]:
        result = []
        for text in texts:
            label, confidence = self.answers[text]
            result.append(Prediction(label, confidence, ((label, confidence),)))
        return result


def categorizer(answers: dict[str, tuple[int, float]] | None) -> HybridCategorizer:
    model = FakeClassifier(answers) if answers is not None else None
    return HybridCategorizer(CATEGORIES, RULES, model, min_confidence=0.6, conflict_confidence=0.8)


@pytest.mark.parametrize(
    ("description", "ml_answer", "category", "source", "kind", "review"),
    [
        ("Евроопт", (GROCERIES, 0.9), GROCERIES, RULE, DecisionKind.RULE_AND_ML_AGREE, False),
        ("Столовая БГУИР", (CAFE, 0.7), CAFE, RULE, DecisionKind.RULES_RESOLVED_BY_ML, False),
        ("Евроопт", (CAFE, 0.95), GROCERIES, RULE, DecisionKind.CONFLICT, True),
        ("Евроопт", (CAFE, 0.5), GROCERIES, RULE, DecisionKind.RULE_ONLY, False),
        ("ИП Петров", (GROCERIES, 0.75), GROCERIES, ML, DecisionKind.ML, False),
        ("ИП Петров", (GROCERIES, 0.3), OTHER, FALLBACK, DecisionKind.LOW_CONFIDENCE, True),
    ],
)  # fmt: skip
def test_arbitration(description, ml_answer, category, source, kind, review) -> None:
    decision = categorizer({description: ml_answer}).categorize(description, EXPENSE)

    assert (decision.category_id, decision.source, decision.kind, decision.needs_review) == (
        category,
        source,
        kind,
        review,
    )


def test_several_rules_without_ml_take_the_longest_keyword() -> None:
    decision = categorizer(None).categorize("Столовая БГУИР", EXPENSE)

    # "столовая" (8 letters) is longer than "бгуир" (5): the more specific rule wins.
    assert (decision.category_id, decision.kind) == (CAFE, DecisionKind.RULE_ONLY)


def test_no_rules_and_no_model_use_the_fallback_of_the_same_type() -> None:
    expense = categorizer(None).categorize("Что-то", EXPENSE)
    income = categorizer(None).categorize("Что-то", INCOME)

    assert (expense.category_id, income.category_id) == (OTHER, OTHER_INCOME)
    assert expense.kind is DecisionKind.NO_INFORMATION and expense.needs_review


def test_confidence_is_the_model_probability_of_the_chosen_category() -> None:
    agree = categorizer({"Евроопт": (GROCERIES, 0.9)}).categorize("Евроопт", EXPENSE)
    conflict = categorizer({"Евроопт": (CAFE, 0.95)}).categorize("Евроопт", EXPENSE)
    rules_only = categorizer(None).categorize("Евроопт", EXPENSE)

    assert agree.confidence == 0.9
    assert conflict.confidence is None  # the model gave the rule's category no probability
    assert rules_only.confidence is None


def test_trace_describes_every_step() -> None:
    decision = categorizer({"Столовая БГУИР": (CAFE, 0.7)}).categorize("Столовая БГУИР", EXPENSE)

    rules, ml, arbiter = decision.trace["steps"]
    assert [step["component"] for step in decision.trace["steps"]] == ["rules", "ml", "arbiter"]
    assert [item["keyword"] for item in rules["result"]] == ["столовая", "бгуир"]
    assert ml["result"]["category"] == "Кафе"
    assert arbiter["decision"] == "rules_resolved_by_ml"
    assert arbiter["category"] == "Кафе"
    assert arbiter["reason"]
    assert decision.trace["thresholds"] == {"ml_min_confidence": 0.6, "ml_conflict_confidence": 0.8}


def test_trace_mentions_missing_model() -> None:
    decision = categorizer(None).categorize("Евроопт", EXPENSE)

    assert decision.trace["steps"][1] == {
        "component": "ml",
        "result": None,
        "note": "модель не обучена",
    }
