"""add categorization decision fields

Revision ID: 6b7c8ccb68e0
Revises: f7b4e05b5fbb
Create Date: 2026-11-03 19:38:56.937734

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6b7c8ccb68e0"
down_revision: str | Sequence[str] | None = "f7b4e05b5fbb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_SOURCES = ("manual", "rule", "ml")
NEW_SOURCES = ("manual", "rule", "ml", "fallback")


def category_source_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values, name="category_source", native_enum=False, create_constraint=True, length=16
    )


def upgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_confidence", sa.Float(), nullable=True))
        # sa.false() renders correctly for both SQLite (0) and PostgreSQL (false).
        batch_op.add_column(
            sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("categorization_trace", sa.JSON(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_transactions_needs_review"), ["needs_review"], unique=False
        )
        batch_op.alter_column(
            "category_source",
            existing_type=category_source_enum(OLD_SOURCES),
            type_=category_source_enum(NEW_SOURCES),
            existing_nullable=True,
        )


def downgrade() -> None:
    op.execute(
        "UPDATE transactions SET category_source = NULL WHERE category_source = 'fallback'"
    )
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.alter_column(
            "category_source",
            existing_type=category_source_enum(NEW_SOURCES),
            type_=category_source_enum(OLD_SOURCES),
            existing_nullable=True,
        )
        batch_op.drop_index(batch_op.f("ix_transactions_needs_review"))
        batch_op.drop_column("categorization_trace")
        batch_op.drop_column("needs_review")
        batch_op.drop_column("category_confidence")
