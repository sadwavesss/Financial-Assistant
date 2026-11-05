"""Statistical component of categorization: a text classifier of transaction descriptions.

TF-IDF over character n-grams (2-5 characters inside word boundaries) + logistic regression.
Character n-grams suit short merchant names written in Cyrillic and Latin ("Евроопт",
"EVROOPT MINSK") and tolerate typos and branch suffixes. Labels are category ids.
"""

import datetime as dt
import json
from collections.abc import Collection, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.utils.text import normalize_text

MODEL_FILE = "categorizer.joblib"
METADATA_FILE = "categorizer.json"
TOP_ALTERNATIVES = 3


@dataclass(frozen=True)
class Prediction:
    label: int
    confidence: float  # probability of `label` among the allowed labels (0..1)
    alternatives: tuple[tuple[int, float], ...]  # top labels with probabilities, best first


@dataclass(frozen=True)
class ModelInfo:
    trained_at: str
    samples: int
    classes: int
    sklearn_version: str


class TextClassifier:
    def __init__(self, pipeline: Pipeline, info: ModelInfo) -> None:
        self.pipeline = pipeline
        self.info = info

    @classmethod
    def train(cls, texts: Sequence[str], labels: Sequence[int]) -> "TextClassifier":
        if len(set(labels)) < 2:
            raise ValueError("At least two different categories are needed to train the model")
        pipeline = Pipeline(
            [
                (
                    "tfidf",
                    TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                ),
                # class_weight: rare categories are not drowned out by frequent ones.
                ("model", LogisticRegression(max_iter=2000, C=10.0, class_weight="balanced")),
            ]
        )
        pipeline.fit([normalize_text(text) for text in texts], list(labels))
        info = ModelInfo(
            trained_at=dt.datetime.now().isoformat(timespec="seconds"),
            samples=len(texts),
            classes=len(set(labels)),
            sklearn_version=sklearn.__version__,
        )
        return cls(pipeline, info)

    @property
    def labels(self) -> list[int]:
        return [int(label) for label in self.pipeline.classes_]

    def predict(
        self, texts: Sequence[str], allowed: Sequence[Collection[int]]
    ) -> list[Prediction | None]:
        """Best label for each text among its allowed labels (categories of the same type).

        Probabilities are renormalized over the allowed labels; None if none of them is known
        to the model.
        """
        if not texts:
            return []
        probabilities = self.pipeline.predict_proba([normalize_text(text) for text in texts])
        classes = np.array(self.labels)
        predictions: list[Prediction | None] = []
        for row, allowed_labels in zip(probabilities, allowed, strict=True):
            mask = np.isin(classes, list(allowed_labels))
            if not mask.any() or row[mask].sum() == 0:
                predictions.append(None)
                continue
            scores = np.where(mask, row, 0.0) / row[mask].sum()
            order = np.argsort(scores)[::-1][:TOP_ALTERNATIVES]
            top = tuple((int(classes[i]), round(float(scores[i]), 4)) for i in order if mask[i])
            predictions.append(Prediction(top[0][0], top[0][1], top))
        return predictions

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, directory / MODEL_FILE)
        (directory / METADATA_FILE).write_text(
            json.dumps(asdict(self.info), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, directory: Path) -> "TextClassifier | None":
        """Load a saved model; None if there is none. Only files written by `save` are loaded."""
        model_path, metadata_path = directory / MODEL_FILE, directory / METADATA_FILE
        if not model_path.is_file() or not metadata_path.is_file():
            return None
        info = ModelInfo(**json.loads(metadata_path.read_text(encoding="utf-8")))
        return cls(joblib.load(model_path), info)
