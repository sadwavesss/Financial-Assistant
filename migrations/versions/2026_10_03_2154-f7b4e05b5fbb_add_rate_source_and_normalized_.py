"""add rate source and normalized description

Revision ID: f7b4e05b5fbb
Revises: eaacdd426377
Create Date: 2026-10-03 21:54:07.897496

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7b4e05b5fbb"
down_revision: str | Sequence[str] | None = "eaacdd426377"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_RATE_SOURCES = ("nbrb", "manual")
NEW_RATE_SOURCES = ("nbrb", "cbr", "currency_api", "manual", "history")


def rate_source_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values, name="rate_source", native_enum=False, create_constraint=True, length=16
    )


def normalize_text(value: str) -> str:
    # Frozen copy of app.utils.text.normalize_text: migrations must not depend on app code.
    return re.sub(r"\s+", " ", value.lower().replace("ё", "е")).strip()


def upgrade() -> None:
    with op.batch_alter_table("transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rate_source", rate_source_enum(NEW_RATE_SOURCES)))
        batch_op.add_column(
            sa.Column(
                "description_normalized", sa.String(length=255), nullable=False, server_default=""
            )
        )

    # Fill the new column for existing rows (SQL lower() does not handle Cyrillic in SQLite).
    connection = op.get_bind()
    transactions = sa.table(
        "transactions", sa.column("id"), sa.column("description"), sa.column("description_normalized")
    )
    for row_id, description in connection.execute(
        sa.select(transactions.c.id, transactions.c.description)
    ):
        connection.execute(
            transactions.update()
            .where(transactions.c.id == row_id)
            .values(description_normalized=normalize_text(description))
        )

    # Existing USD operations could only get their rate from NBRB before this revision.
    connection.execute(
        sa.text("UPDATE transactions SET rate_source = 'nbrb' WHERE currency = 'USD'")
    )

    with op.batch_alter_table("exchange_rates", schema=None) as batch_op:
        batch_op.alter_column(
            "source",
            existing_type=rate_source_enum(OLD_RATE_SOURCES),
            type_=rate_source_enum(NEW_RATE_SOURCES),
            existing_nullable=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM exchange_rates WHERE source NOT IN ('nbrb', 'manual')")
    )
    with op.batch_alter_table("exchange_rates", schema=None) as batch_op:
        batch_op.alter_column(
            "source",
            existing_type=rate_source_enum(NEW_RATE_SOURCES),
            type_=rate_source_enum(OLD_RATE_SOURCES),
            existing_nullable=False,
        )

    with op.batch_alter_table("transactions", schema=None) as batch_op:
        # The CHECK constraint of the enum must go first, otherwise it references a missing column.
        batch_op.drop_constraint(op.f("ck_transactions_rate_source"), type_="check")
        batch_op.drop_column("description_normalized")
        batch_op.drop_column("rate_source")
