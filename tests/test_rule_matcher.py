"""Symbolic component: keyword matching rules."""

import pytest

from app.models import TransactionType
from app.services.rule_matcher import KeywordRule, RuleMatcher

EXPENSE, INCOME = TransactionType.EXPENSE, TransactionType.INCOME
GROCERIES, HOME, EDUCATION, CAFE, SALARY = 1, 2, 3, 4, 5

matcher = RuleMatcher(
    [
        KeywordRule("евроопт", GROCERIES, EXPENSE),
        KeywordRule("ома", HOME, EXPENSE),
        KeywordRule("oma", HOME, EXPENSE),
        KeywordRule("бгуир", EDUCATION, EXPENSE),
        KeywordRule("столовая бгуир", CAFE, EXPENSE),
        KeywordRule("кафе", CAFE, EXPENSE),
        KeywordRule("life:)", 6, EXPENSE),
        KeywordRule("зарплата", SALARY, INCOME),
    ]
)


def ids(description: str, kind: TransactionType = EXPENSE) -> list[int]:
    return [candidate.category_id for candidate in matcher.match(description, kind)]


@pytest.mark.parametrize("description", ["ЕВРООПТ Минск", "оплата: Евроопт.", "евроопт"])
def test_case_insensitive_whole_word(description: str) -> None:
    assert ids(description) == [GROCERIES]


@pytest.mark.parametrize("description", ["Ромашка", "Домашний текстиль", "Oman Air"])
def test_keyword_inside_another_word_does_not_match(description: str) -> None:
    assert ids(description) == []


def test_yo_is_treated_as_e() -> None:
    assert [
        c.keyword
        for c in RuleMatcher([KeywordRule("рублевский", 1, EXPENSE)]).match("Рублёвский", EXPENSE)
    ] == ["рублевский"]


def test_longest_keyword_comes_first_and_all_candidates_are_returned() -> None:
    candidates = matcher.match("Столовая БГУИР, кафе", EXPENSE)

    assert [(c.category_id, c.keyword) for c in candidates] == [
        (CAFE, "столовая бгуир"),
        (EDUCATION, "бгуир"),
    ]


def test_only_categories_of_the_same_type() -> None:
    assert ids("Зарплата за май", EXPENSE) == []
    assert ids("Зарплата за май", INCOME) == [SALARY]


def test_keywords_with_punctuation() -> None:
    assert ids("Пополнение life:) 375291234567") == [6]
