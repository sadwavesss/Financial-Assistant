"""Categories of transactions and keyword rules for automatic categorization."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import TransactionType, enum_type
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("name", "type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[TransactionType] = mapped_column(enum_type(TransactionType, "category_type"))
    color: Mapped[str] = mapped_column(String(7), default="#6c757d")
    is_system: Mapped[bool] = mapped_column(default=False)

    # passive_deletes: the database itself applies ON DELETE CASCADE / SET NULL,
    # so deleting a category does not load all its rules and transactions into memory.
    rules: Mapped[list["CategoryRule"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CategoryRule.keyword",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="category", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"Category(id={self.id}, name={self.name!r}, type={self.type.value})"


class CategoryRule(TimestampMixin, Base):
    """A keyword: if a transaction description contains it, the category is assigned."""

    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    # Stored normalized (lower case, "ё" -> "е"), unique across all categories.
    keyword: Mapped[str] = mapped_column(String(100), unique=True)

    category: Mapped[Category] = relationship(back_populates="rules")

    def __repr__(self) -> str:
        return f"CategoryRule(id={self.id}, keyword={self.keyword!r})"
