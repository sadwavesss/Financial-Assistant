"""Knowledge bases stored as data files (edited without changing the code)."""

import json
from functools import lru_cache
from pathlib import Path

from app.services.inference import KnowledgeBase

RECOMMENDATION_RULES = Path(__file__).with_name("recommendation_rules.json")


@lru_cache
def load_recommendation_rules(path: Path = RECOMMENDATION_RULES) -> KnowledgeBase:
    """Load and validate the recommendation knowledge base (errors surface immediately)."""
    return KnowledgeBase.model_validate(json.loads(path.read_text(encoding="utf-8")))
