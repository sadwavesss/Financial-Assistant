"""Category schemas."""

from pydantic import BaseModel, ConfigDict

from app.models import TransactionType


class CategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: TransactionType
    color: str


class CategoryOut(CategoryBrief):
    is_system: bool
