"""Category and keyword rule schemas."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import TransactionType

HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class CategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: TransactionType
    color: str


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str


class CategoryOut(CategoryBrief):
    is_system: bool
    rules: list[RuleOut]


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    color: HexColor = "#6c757d"


class CategoryIn(CategoryUpdate):
    type: TransactionType


class RuleIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
