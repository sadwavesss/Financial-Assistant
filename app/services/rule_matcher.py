"""Symbolic component of categorization: matching descriptions against the keyword knowledge base.

A keyword matches only as a whole word or phrase ("ома" does not match "ромашка"), only among
categories of the same transaction type, and case/"ё"-insensitively. If keywords of several
categories match, all of them are returned as candidates, the longest (most specific) first.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.models import TransactionType
from app.utils.text import normalize_text


@dataclass(frozen=True)
class KeywordRule:
    keyword: str  # normalized
    category_id: int
    category_type: TransactionType


@dataclass(frozen=True)
class RuleCandidate:
    category_id: int
    keyword: str  # the longest matched keyword of this category


class RuleMatcher:
    def __init__(self, rules: Iterable[KeywordRule]) -> None:
        self._rules = [
            (rule, re.compile(rf"(?<!\w){re.escape(rule.keyword)}(?!\w)"))
            for rule in sorted(rules, key=lambda r: (-len(r.keyword), r.keyword))
        ]

    def __len__(self) -> int:
        return len(self._rules)

    def match(self, description: str, transaction_type: TransactionType) -> list[RuleCandidate]:
        """Candidate categories, the most specific (longest keyword) first; [] if none."""
        text = normalize_text(description)
        candidates: dict[int, RuleCandidate] = {}
        for rule, pattern in self._rules:  # already sorted by keyword length
            if rule.category_type is not transaction_type or rule.category_id in candidates:
                continue
            if pattern.search(text):
                candidates[rule.category_id] = RuleCandidate(rule.category_id, rule.keyword)
        return list(candidates.values())
