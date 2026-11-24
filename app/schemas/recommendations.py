"""Schemas of the recommendations API."""

from typing import Any

from pydantic import BaseModel

from app.services.recommendations import RecommendationReport


class ExplanationOut(BaseModel):
    text: str
    passed: bool


class RecommendationOut(BaseModel):
    rule_id: str
    severity: str
    title: str
    text: str
    category: str | None
    explanation: list[ExplanationOut]


class FiringOut(BaseModel):
    pass_number: int
    rule_id: str
    description: str
    binding: str | None
    derived: dict[str, Any] | None


class RecommendationsOut(BaseModel):
    recommendations: list[RecommendationOut]
    facts: dict[str, Any]
    passes: int
    firings: list[FiringOut]

    @classmethod
    def from_report(cls, report: RecommendationReport) -> "RecommendationsOut":
        return cls(
            recommendations=[
                RecommendationOut(
                    rule_id=r.rule_id,
                    severity=r.severity,
                    title=r.title,
                    text=r.text,
                    category=r.binding,
                    explanation=[
                        ExplanationOut(text=e.text, passed=e.passed) for e in r.explanation
                    ],
                )
                for r in report.recommendations
            ],
            facts=report.facts,
            passes=report.result.passes,
            firings=[
                FiringOut(
                    pass_number=f.pass_number,
                    rule_id=f.rule.id,
                    description=f.rule.description,
                    binding=f.binding,
                    derived={"fact": f.derived[0], "value": f.derived[1]} if f.derived else None,
                )
                for f in report.result.firings
            ],
        )
