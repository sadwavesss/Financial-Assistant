"""Budget recommendations: facts from analytics, forecast and recurring payments + rule inference.

Facts describe the last complete month (compared with the three months before it), the current
month (forecast and spending pace) and recurring payments. Each fact keeps its source, so the
explanation of a recommendation shows which component (statistical or symbolic) produced it.
"""

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.knowledge import load_recommendation_rules
from app.models import Category, Transaction, TransactionType
from app.services.analytics import Granularity
from app.services.errors import InvalidDataError
from app.services.forecast import build_forecast
from app.services.inference import Check, Firing, InferenceResult, KnowledgeBase, infer
from app.services.recurring import find_recurring
from app.utils.dates import add_months
from app.utils.formatting import format_money

SEVERITY_ORDER = {"high": 0, "medium": 1, "info": 2, "positive": 3}
SUBSCRIPTIONS_CATEGORY = "Подписки и сервисы"
MONTHS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
          "октябрь", "ноябрь", "декабрь")  # fmt: skip
OP_LABELS = {"<": "<", "<=": "≤", ">": ">", ">=": "≥", "==": "=", "!=": "≠", "exists": "известно"}
_PLACEHOLDER = re.compile(r"\{([\w.]+)(?:\|(\w+))?\}")


@dataclass(frozen=True)
class ExplanationLine:
    text: str
    passed: bool


@dataclass(frozen=True)
class Recommendation:
    rule_id: str
    severity: str
    title: str
    text: str
    binding: str | None
    explanation: list[ExplanationLine]


@dataclass(frozen=True)
class RecommendationReport:
    today: dt.date
    facts: dict[str, Any]
    result: InferenceResult
    recommendations: list[Recommendation]
    kb: KnowledgeBase

    def fact_rows(self) -> list[tuple[str, str, str]]:
        """(label, formatted value, source) of every known scalar fact, for display."""
        return [
            (info.label, format_fact(self.facts[name], info.format), info.source)
            for name, info in self.kb.facts.items()
            if name in self.facts and name != "categories"
        ]


def build_recommendations(db: Session, today: dt.date | None = None) -> RecommendationReport:
    today = today or dt.date.today()
    kb = load_recommendation_rules()
    facts = collect_facts(db, kb, today)
    result = infer(kb, facts)
    recommendations = [
        _recommendation(kb, firing, result.facts, result.firings)
        for firing in result.recommendations
    ]
    recommendations.sort(
        key=lambda r: (SEVERITY_ORDER[r.severity], _priority(kb, r.rule_id), r.binding or "")
    )
    return RecommendationReport(today, result.facts, result, recommendations, kb)


# ---------- Facts ----------


def collect_facts(db: Session, kb: KnowledgeBase, today: dt.date) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    month = add_months(today.replace(day=1), -1)  # the last complete month
    facts.update(_month_facts(db, kb, month))
    facts.update(_forecast_facts(db, today, facts.get("expense_recent_avg")))
    facts.update(_recurring_facts(db, today))
    facts["needs_review"] = db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.needs_review)
    )
    return {name: value for name, value in facts.items() if value is not None}


def _month_facts(db: Session, kb: KnowledgeBase, month: dt.date) -> dict[str, Any]:
    months = [add_months(month, -back) for back in range(4)]  # month, then 3 months before
    totals: dict[dt.date, dict[TransactionType, float]] = defaultdict(lambda: defaultdict(float))
    by_category: dict[dt.date, dict[int | None, float]] = defaultdict(lambda: defaultdict(float))
    rows = db.execute(
        select(
            Transaction.date, Transaction.type, Transaction.category_id, Transaction.amount_byn
        ).where(Transaction.date.between(months[-1], add_months(month, 1) - dt.timedelta(days=1)))
    ).all()
    for day, kind, category_id, amount in rows:
        start = day.replace(day=1)
        totals[start][kind] += float(amount)
        if kind is TransactionType.EXPENSE:
            by_category[start][category_id] += float(amount)

    income = totals[month][TransactionType.INCOME]
    expense = totals[month][TransactionType.EXPENSE]
    if not income and not expense:
        return {}
    previous = [totals[m][TransactionType.EXPENSE] for m in months[1:]]
    recent = months[:3]
    recent_income = sum(totals[m][TransactionType.INCOME] for m in recent)
    recent_expense = sum(totals[m][TransactionType.EXPENSE] for m in recent)
    recent_with_data = [m for m in recent if totals[m][TransactionType.EXPENSE]]
    avg3 = sum(previous) / 3 if any(previous) else None

    names = {c.id: c.name for c in db.scalars(select(Category))}
    needs = set(kb.category_groups.get("needs", []))
    categories = []
    for category_id, amount in sorted(by_category[month].items(), key=lambda kv: -kv[1]):
        name = names.get(category_id, "Без категории")
        cat_avg = sum(by_category[m].get(category_id, 0.0) for m in months[1:]) / 3
        categories.append({
            "name": name,
            "amount": amount,
            "share": amount / expense if expense else 0.0,
            "avg3": cat_avg,
            "growth": amount / cat_avg - 1 if cat_avg else None,
            "group": "needs" if name in needs else "wants",
        })  # fmt: skip
    needs_amount = sum(c["amount"] for c in categories if c["group"] == "needs")

    return {
        "month_label": f"{MONTHS[month.month - 1]} {month.year}",
        "income_month": income,
        "expense_month": expense,
        "balance_month": income - expense,
        "deficit_amount": expense - income if expense > income else None,
        "savings_rate_month": (income - expense) / income if income else None,
        "savings_rate_avg": (recent_income - recent_expense) / recent_income
        if recent_income
        else None,
        "expense_avg3": avg3,
        "expense_change": expense / avg3 - 1 if avg3 else None,
        "expense_recent_avg": recent_expense / len(recent_with_data) if recent_with_data else None,
        "needs_share": needs_amount / expense if expense else None,
        "wants_share": (expense - needs_amount) / expense if expense else None,
        "categories": categories,
    }


def _forecast_facts(db: Session, today: dt.date, recent_avg: float | None) -> dict[str, Any]:
    try:
        report = build_forecast(db, Granularity.MONTH, 1, today=today, category_limit=0)
    except InvalidDataError:
        return {}  # not enough history: forecast facts stay unknown
    current = report.current_forecast
    if current is None or current.value <= 0:
        return {}
    spent_share = report.current_spent / current.value
    return {
        "forecast_current": current.value,
        "forecast_model": report.result.best.label,
        "forecast_vs_recent": current.value / recent_avg - 1 if recent_avg else None,
        "current_spent": report.current_spent,
        "current_elapsed": report.current_elapsed,
        "pace_ratio": spent_share / report.current_elapsed if report.current_elapsed else None,
    }


def _recurring_facts(db: Session, today: dt.date) -> dict[str, Any]:
    report = find_recurring(db, 12, today)
    active = report.of_type(TransactionType.EXPENSE)
    subscriptions = [p for p in active if p.category and p.category.name == SUBSCRIPTIONS_CATEGORY]
    soon = [p for p in report.upcoming(7) if p.type is TransactionType.EXPENSE]
    stopped = [p for p in report.payments if not p.active and p.type is TransactionType.EXPENSE]
    return {
        "recurring_monthly": float(report.monthly_recurring_expense) if active else None,
        "recurring_share": report.recurring_share if active else None,
        "subscriptions_count": len(subscriptions),
        "subscription_names": [p.name for p in subscriptions],
        "upcoming_7d_amount": float(sum(p.typical_amount_byn for p in soon)),
        "upcoming_7d_names": [f"{p.name} ({p.next_date:%d.%m})" for p in soon],
        "stopped_count": len(stopped),
        "stopped_names": [p.name for p in stopped],
    }


# ---------- Formatting and explanations ----------


def format_fact(value: Any, kind: str) -> str:
    if value is None:
        return "нет данных"
    if kind == "money" and isinstance(value, int | float | Decimal):
        return f"{format_money(Decimal(str(round(value, 2))))} BYN"
    if kind == "percent" and isinstance(value, int | float):
        return f"{value * 100:.0f}%"
    if kind == "int" and isinstance(value, int | float):
        return str(int(value))
    if kind == "list" and isinstance(value, list):
        return ", ".join(map(str, value)) or "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    return str(value)


def render_template(template: str, kb: KnowledgeBase, facts: dict[str, Any]) -> str:
    """Fill {fact} and {fact|format} placeholders; an unknown fact is shown as "нет данных"."""

    def substitute(match: re.Match) -> str:
        name, kind = match.group(1), match.group(2) or kb.fact_format(match.group(1))
        return format_fact(facts.get(name), kind)

    return _PLACEHOLDER.sub(substitute, template)


def _recommendation(
    kb: KnowledgeBase, firing: Firing, facts: dict[str, Any], firings: list[Firing]
) -> Recommendation:
    context = dict(facts)
    if firing.binding is not None:
        item = next(c for c in facts.get("categories", []) if c["name"] == firing.binding)
        context.update({f"category.{key}": value for key, value in item.items()})
    recommend = firing.rule.then.recommend
    return Recommendation(
        rule_id=firing.rule.id,
        severity=recommend.severity,
        title=render_template(recommend.title, kb, context),
        text=render_template(recommend.text, kb, context),
        binding=firing.binding,
        explanation=_explain(kb, firing, firings),
    )


def _explain(kb: KnowledgeBase, firing: Firing, firings: list[Firing]) -> list[ExplanationLine]:
    """Checks of the rule; for a fact derived by another rule, that rule's checks follow
    (indented), so the whole chain of reasoning is visible."""
    derived_by = {f.derived[0]: f for f in firings if f.derived}
    lines: list[ExplanationLine] = []

    def add(current: Firing, depth: int, seen: frozenset[str]) -> None:
        for check in current.checks:
            prefix = "    " * depth
            lines.append(ExplanationLine(prefix + _check_text(kb, check), check.passed))
            source = derived_by.get(check.fact)
            if check.passed and source is not None and source.rule.id not in seen:
                lines.append(
                    ExplanationLine(
                        f"{prefix}    ↳ выведено правилом {source.rule.id}: "
                        f"{source.rule.description}",
                        True,
                    )
                )
                add(source, depth + 1, seen | {source.rule.id})

    add(firing, 0, frozenset({firing.rule.id}))
    return lines


def _check_text(kb: KnowledgeBase, check: Check) -> str:
    kind = kb.fact_format(check.fact)
    actual = format_fact(check.actual, kind)
    if check.op == "exists":
        return f"{kb.label(check.fact)}: {actual}"
    negated = check.op.startswith("not ")
    op = OP_LABELS.get(check.op.removeprefix("not "), check.op)
    if check.reference:
        expected = f"{kb.label(check.reference)} ({format_fact(check.expected, kind)})"
    else:
        expected = format_fact(
            check.expected, kind if not isinstance(check.expected, bool) else "bool"
        )
    if negated:
        return f"неверно, что «{kb.label(check.fact)}» {op} {expected} (сейчас: {actual})"
    return f"{kb.label(check.fact)} = {actual} {op} {expected}"


def _priority(kb: KnowledgeBase, rule_id: str) -> int:
    return next(rule.priority for rule in kb.rules if rule.id == rule_id)
