"""Inference engine: conditions, missing facts, forward chaining, category scope, validation."""

import pytest
from pydantic import ValidationError

from app.knowledge import load_recommendation_rules
from app.services.inference import KnowledgeBase, infer


def kb(rules: list[dict], facts: tuple[str, ...] = ("a", "b", "c")) -> KnowledgeBase:
    return KnowledgeBase.model_validate(
        {
            "facts": {name: {"label": name} for name in facts},
            "category_facts": {"name": {"label": "name"}, "share": {"label": "share"}},
            "rules": rules,
        }
    )


def recommend(rule_id: str, when: dict, **extra) -> dict:
    return {
        "id": rule_id,
        "description": rule_id,
        "when": when,
        "then": {"recommend": {"severity": "info", "title": rule_id, "text": "-"}},
        **extra,
    }


def derive(rule_id: str, when: dict, fact: str, priority: int = 100) -> dict:
    return {"id": rule_id, "description": rule_id, "priority": priority, "when": when,
            "then": {"derive": {"fact": fact, "value": True}}}  # fmt: skip


def fired(base: KnowledgeBase, facts: dict) -> list[str]:
    return [f.rule.id for f in infer(base, facts).firings]


@pytest.mark.parametrize(
    ("when", "facts", "expected"),
    [
        ({"fact": "a", "op": ">", "value": 10}, {"a": 11}, True),
        ({"fact": "a", "op": ">", "value": 10}, {"a": 10}, False),
        ({"fact": "a", "op": "<=", "value": 10}, {"a": 10}, True),
        ({"fact": "a", "op": "==", "value": "x"}, {"a": "x"}, True),
        ({"fact": "a", "op": ">", "fact_ref": "b", "factor": 1.5}, {"a": 16, "b": 10}, True),
        ({"fact": "a", "op": ">", "fact_ref": "b", "factor": 1.5}, {"a": 14, "b": 10}, False),
        ({"fact": "a", "op": "exists"}, {"a": 0}, True),
        ({"all": [{"fact": "a", "op": ">", "value": 1}, {"fact": "b", "op": ">", "value": 1}]},
         {"a": 2, "b": 0}, False),
        ({"any": [{"fact": "a", "op": ">", "value": 1}, {"fact": "b", "op": ">", "value": 1}]},
         {"a": 2, "b": 0}, True),
        ({"not": {"fact": "a", "op": ">", "value": 1}}, {"a": 0}, True),
    ],
)  # fmt: skip
def test_conditions(when: dict, facts: dict, expected: bool) -> None:
    assert (fired(kb([recommend("R", when)]), facts) == ["R"]) is expected


def test_missing_fact_makes_comparison_false_and_is_traced() -> None:
    result = infer(kb([recommend("R", {"fact": "a", "op": "<", "value": 5})]), {"a": None})

    assert result.firings == []
    assert "a" not in result.facts  # None values are not facts at all


def test_type_mismatch_is_not_satisfied() -> None:
    assert fired(kb([recommend("R", {"fact": "a", "op": ">", "value": 5})]), {"a": "text"}) == []


def test_forward_chaining_across_passes() -> None:
    # R needs "y", which needs "x"; rules are listed in the "wrong" order on purpose.
    base = kb(
        [
            recommend("R", {"fact": "y", "op": "==", "value": True}, priority=1),
            derive("D2", {"fact": "x", "op": "==", "value": True}, "y", priority=2),
            derive("D1", {"fact": "a", "op": ">", "value": 0}, "x", priority=3),
        ]
    )

    result = infer(base, {"a": 1})

    assert [(f.rule.id, f.pass_number) for f in result.firings] == [("D1", 1), ("D2", 2), ("R", 3)]
    assert result.facts["y"] is True
    # Within a pass rules go by priority, so a fact derived earlier is visible to later rules of
    # the same pass. Here each step waits for the next pass; pass 3 derives nothing -> stop.
    assert result.passes == 3


def test_every_rule_fires_once_and_inference_terminates() -> None:
    base = kb([derive("D", {"fact": "a", "op": ">", "value": 0}, "x")])

    result = infer(base, {"a": 1})

    assert [f.rule.id for f in result.firings] == ["D"]
    assert result.passes == 2


def test_category_scoped_rule_fires_per_category() -> None:
    base = kb(
        [recommend("R", {"fact": "category.share", "op": ">", "value": 0.3}, scope="category")]
    )
    categories = [
        {"name": "A", "share": 0.5},
        {"name": "B", "share": 0.1},
        {"name": "C", "share": 0.4},
    ]

    result = infer(base, {"categories": categories})

    assert [f.binding for f in result.firings] == ["A", "C"]


def test_checks_record_actual_and_expected_values() -> None:
    base = kb([recommend("R", {"fact": "a", "op": ">", "fact_ref": "b", "factor": 2})])

    (firing,) = infer(base, {"a": 5, "b": 2}).firings

    (check,) = firing.checks
    assert (check.fact, check.actual, check.expected, check.reference) == ("a", 5, 4, "b")


@pytest.mark.parametrize(
    "bad_rule",
    [
        recommend("R", {"fact": "unknown", "op": ">", "value": 1}),
        recommend("R", {"fact": "a", "op": "~", "value": 1}),
        recommend("R", {"fact": "a", "op": ">"}),  # no operand
        {"id": "R", "description": "-", "when": {"fact": "a", "op": ">", "value": 1}, "then": {}},
        recommend("R", {"fact": "category.share", "op": ">", "value": 1}),  # global scope
    ],
)
def test_invalid_knowledge_base_is_rejected(bad_rule: dict) -> None:
    with pytest.raises(ValidationError):
        kb([bad_rule])


def test_duplicate_rule_ids_are_rejected() -> None:
    rule = recommend("R", {"fact": "a", "op": ">", "value": 1})

    with pytest.raises(ValidationError, match="unique"):
        kb([rule, rule])


def test_project_knowledge_base_is_valid() -> None:
    base = load_recommendation_rules()

    assert len(base.rules) >= 15
    assert {"needs", "wants"} <= set(base.category_groups)
    derived = {r.then.derive.fact for r in base.rules if r.then.derive}
    assert derived <= set(base.facts)  # every derived fact has a Russian label
