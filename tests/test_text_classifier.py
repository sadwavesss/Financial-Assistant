"""Statistical component: training, prediction restricted to allowed labels, persistence."""

from pathlib import Path

import pytest

from app.ml.text_classifier import TextClassifier

GROCERIES, CAFE, SALARY = 1, 2, 3
TEXTS = ["Евроопт Минск", "EVROOPT MINSK", "Гиппо", "Кофейня Зерно", "Coffee Break", "Кофейня Арт",
         "Зарплата ООО", "Заработная плата", "Зарплата за май"]  # fmt: skip
LABELS = [GROCERIES] * 3 + [CAFE] * 3 + [SALARY] * 3


@pytest.fixture(scope="module")
def classifier() -> TextClassifier:
    return TextClassifier.train(TEXTS, LABELS)


def test_predicts_similar_descriptions(classifier: TextClassifier) -> None:
    (groceries, cafe) = classifier.predict(
        ["EVROOPT GRODNO", "Кофейня у метро"], [{GROCERIES, CAFE}, {GROCERIES, CAFE}]
    )

    assert groceries.label == GROCERIES
    assert cafe.label == CAFE
    assert 0 < cafe.confidence <= 1
    assert cafe.alternatives[0] == (cafe.label, cafe.confidence)


def test_only_allowed_labels_are_returned_and_renormalized(classifier: TextClassifier) -> None:
    (prediction,) = classifier.predict(["Зарплата"], [{GROCERIES, CAFE}])

    assert prediction.label in {GROCERIES, CAFE}
    assert sum(p for _, p in prediction.alternatives) == pytest.approx(1, abs=1e-3)


def test_no_known_allowed_label_gives_none(classifier: TextClassifier) -> None:
    assert classifier.predict(["Евроопт"], [{99}]) == [None]


def test_save_and_load_give_the_same_predictions(
    classifier: TextClassifier, tmp_path: Path
) -> None:
    classifier.save(tmp_path)
    loaded = TextClassifier.load(tmp_path)

    allowed = [{GROCERIES, CAFE, SALARY}]
    assert loaded.predict(["Гиппо Минск"], allowed) == classifier.predict(["Гиппо Минск"], allowed)
    assert loaded.info == classifier.info


def test_load_without_files_returns_none(tmp_path: Path) -> None:
    assert TextClassifier.load(tmp_path) is None


def test_one_class_cannot_be_trained() -> None:
    with pytest.raises(ValueError):
        TextClassifier.train(["a", "b"], [1, 1])
