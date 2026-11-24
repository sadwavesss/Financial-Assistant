"""A small production-rule inference engine with forward chaining and a full trace.

Knowledge base format (validated on load):

    condition := {"all": [condition, ...]} | {"any": [condition, ...]} | {"not": condition}
               | {"fact": name, "op": "<"|"<="|">"|">="|"=="|"!=", "value": number|bool|str}
               | {"fact": name, "op": ..., "fact_ref": other_name, "factor": number}
               | {"fact": name, "op": "exists"}
    rule      := {"id", "priority", "scope": "global"|"category", "when": condition,
                  "then": {"derive": {"fact", "value"}} | {"recommend": {...}}}

Rules with scope "category" are checked once per item of the `categories` fact; inside them
the item's fields are available as "category.<field>".

Forward chaining: all rules are checked against the facts; a fired rule may derive a new fact,
which can make other rules fire on the next pass. The engine stops when a pass derives nothing
new. Every rule fires at most once per binding (category), so the process always terminates.
A missing fact makes its comparison false; the trace records it as "no data".
"""

import operator
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

OPERATORS = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}
MAX_PASSES = 10
CATEGORY_PREFIX = "category."


# ---------- Knowledge base schema ----------


class Comparison(BaseModel):
    fact: str
    op: Literal["<", "<=", ">", ">=", "==", "!=", "exists"]
    value: float | bool | str | None = None
    fact_ref: str | None = None  # compare with another fact...
    factor: float = 1.0  # ...multiplied by this factor

    @model_validator(mode="after")
    def operand_is_given(self) -> "Comparison":
        if self.op != "exists" and (self.value is None) == (self.fact_ref is None):
            raise ValueError(f"comparison of '{self.fact}' needs exactly one of value / fact_ref")
        return self


class AllOf(BaseModel):
    all: list["Condition"]


class AnyOf(BaseModel):
    any: list["Condition"]


class NotOf(BaseModel):
    not_: "Condition" = Field(alias="not")


Condition = Annotated[Comparison | AllOf | AnyOf | NotOf, Field(union_mode="left_to_right")]
for _model in (AllOf, AnyOf, NotOf):  # resolve the recursive "Condition" references
    _model.model_rebuild()


class Derive(BaseModel):
    fact: str
    value: float | bool | str


class Recommend(BaseModel):
    severity: Literal["high", "medium", "info", "positive"]
    title: str
    text: str  # placeholders: {fact} or {fact|money} / {fact|percent} / {fact|int}


class Action(BaseModel):
    derive: Derive | None = None
    recommend: Recommend | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "Action":
        if (self.derive is None) == (self.recommend is None):
            raise ValueError("'then' must contain exactly one of 'derive' / 'recommend'")
        return self


class Rule(BaseModel):
    id: str
    description: str
    priority: int = 100  # lower = checked earlier and shown first
    scope: Literal["global", "category"] = "global"
    when: Condition
    then: Action


class FactInfo(BaseModel):
    label: str
    format: Literal["money", "percent", "int", "text", "bool", "list"] = "text"
    source: str = ""


class KnowledgeBase(BaseModel):
    facts: dict[str, FactInfo]
    category_facts: dict[str, FactInfo] = {}
    # Domain classifications used when facts are prepared (e.g. needs / wants for 50/30/20).
    category_groups: dict[str, list[str]] = {}
    rules: list[Rule]

    @model_validator(mode="after")
    def references_are_known(self) -> "KnowledgeBase":
        known = set(self.facts) | {r.then.derive.fact for r in self.rules if r.then.derive}
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        for rule in self.rules:
            scoped = (
                {CATEGORY_PREFIX + f for f in self.category_facts}
                if rule.scope == "category"
                else set()
            )
            for name in _referenced_facts(rule.when):
                if name not in known | scoped:
                    raise ValueError(f"rule '{rule.id}' refers to an unknown fact '{name}'")
        return self

    def label(self, name: str) -> str:
        info = self.facts.get(name) or self.category_facts.get(name.removeprefix(CATEGORY_PREFIX))
        return info.label if info else name

    def fact_format(self, name: str) -> str:
        info = self.facts.get(name) or self.category_facts.get(name.removeprefix(CATEGORY_PREFIX))
        return info.format if info else "text"


def _referenced_facts(condition: Any) -> list[str]:
    if isinstance(condition, Comparison):
        return [condition.fact] + ([condition.fact_ref] if condition.fact_ref else [])
    if isinstance(condition, AllOf):
        return [n for c in condition.all for n in _referenced_facts(c)]
    if isinstance(condition, AnyOf):
        return [n for c in condition.any for n in _referenced_facts(c)]
    return _referenced_facts(condition.not_)


# ---------- Inference ----------


@dataclass(frozen=True)
class Check:
    """One evaluated comparison: what was compared and whether it held."""

    fact: str
    op: str
    expected: Any  # the constant, or the referenced fact's value x factor
    actual: Any  # None = no data
    passed: bool
    reference: str | None = None  # name of the referenced fact, if any


@dataclass(frozen=True)
class Firing:
    rule: Rule
    pass_number: int
    binding: str | None  # category name for category-scoped rules
    checks: list[Check]
    derived: tuple[str, Any] | None = None


@dataclass
class InferenceResult:
    facts: dict[str, Any]
    firings: list[Firing] = field(default_factory=list)
    passes: int = 0

    @property
    def recommendations(self) -> list[Firing]:
        return [f for f in self.firings if f.rule.then.recommend is not None]


def infer(kb: KnowledgeBase, initial_facts: Mapping[str, Any]) -> InferenceResult:
    facts = {name: value for name, value in initial_facts.items() if value is not None}
    result = InferenceResult(facts=facts)
    fired: set[tuple[str, str | None]] = set()
    rules = sorted(kb.rules, key=lambda r: (r.priority, r.id))

    for pass_number in range(1, MAX_PASSES + 1):
        result.passes = pass_number
        derived_something = False
        for rule in rules:
            for binding, context in _bindings(rule, facts):
                if (rule.id, binding) in fired:
                    continue
                checks: list[Check] = []
                if not _evaluate(rule.when, context, checks):
                    continue
                fired.add((rule.id, binding))
                derived = None
                if rule.then.derive is not None:
                    name, value = rule.then.derive.fact, rule.then.derive.value
                    if facts.get(name) != value:
                        facts[name] = value
                        derived_something = True
                    derived = (name, value)
                result.firings.append(Firing(rule, pass_number, binding, checks, derived))
        if not derived_something:
            break
    return result


def _bindings(rule: Rule, facts: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    if rule.scope == "global":
        return [(None, facts)]
    contexts = []
    for item in facts.get("categories", []):
        scoped = {CATEGORY_PREFIX + key: value for key, value in item.items() if value is not None}
        contexts.append((item.get("name"), {**facts, **scoped}))
    return contexts


def _evaluate(condition: Any, facts: Mapping[str, Any], checks: list[Check]) -> bool:
    if isinstance(condition, AllOf):
        results = [_evaluate(c, facts, checks) for c in condition.all]  # all evaluated: full trace
        return all(results)
    if isinstance(condition, AnyOf):
        results = [_evaluate(c, facts, checks) for c in condition.any]
        return any(results)
    if isinstance(condition, NotOf):
        inner: list[Check] = []
        passed = not _evaluate(condition.not_, facts, inner)
        checks.extend(Check(c.fact, f"not {c.op}", c.expected, c.actual, passed, c.reference)
                      for c in inner)  # fmt: skip
        return passed
    return _compare(condition, facts, checks)


def _compare(cmp: Comparison, facts: Mapping[str, Any], checks: list[Check]) -> bool:
    actual = facts.get(cmp.fact)
    if cmp.op == "exists":
        passed = actual is not None
        checks.append(Check(cmp.fact, cmp.op, None, actual, passed))
        return passed
    if cmp.fact_ref is not None:
        reference = facts.get(cmp.fact_ref)
        expected = reference * cmp.factor if isinstance(reference, int | float) else None
    else:
        expected = cmp.value
    passed = False
    if actual is not None and expected is not None:
        try:
            passed = bool(OPERATORS[cmp.op](actual, expected))
        except TypeError:  # e.g. comparing text with a number: treated as not satisfied
            passed = False
    checks.append(Check(cmp.fact, cmp.op, expected, actual, passed, cmp.fact_ref))
    return passed
