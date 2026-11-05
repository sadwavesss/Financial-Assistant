"""Schemas of the categorization API."""

from typing import Any

from pydantic import BaseModel, Field

from app.models import CategorySource, TransactionType


class CategorizeIn(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    type: TransactionType = TransactionType.EXPENSE


class DecisionOut(BaseModel):
    category_id: int | None
    category: str | None
    source: CategorySource
    confidence: float | None
    needs_review: bool
    decision: str
    reason: str
    trace: dict[str, Any]


class ModelStatusOut(BaseModel):
    trained: bool
    trained_at: str | None = None
    samples: int | None = None
    classes: int | None = None
    available_samples: int  # labeled transactions usable for (re)training now
    needs_review: int  # transactions waiting for the user's check


class RecategorizationOut(BaseModel):
    processed: int
    changed: int
    needs_review: int
