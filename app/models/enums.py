"""Enumerations shared by models, schemas and services."""

from enum import StrEnum

from sqlalchemy import Enum


class TransactionType(StrEnum):
    INCOME = "income"
    EXPENSE = "expense"


class Currency(StrEnum):
    BYN = "BYN"
    USD = "USD"


class CategorySource(StrEnum):
    """How the category of a transaction was assigned."""

    MANUAL = "manual"  # chosen by the user
    RULE = "rule"  # matched a keyword rule
    ML = "ml"  # predicted by the classifier


class RateSource(StrEnum):
    NBRB = "nbrb"  # National Bank of the Republic of Belarus API
    MANUAL = "manual"  # entered by the user


def enum_type(enum_cls: type[StrEnum], name: str) -> Enum:
    """Portable enum column: VARCHAR + CHECK constraint storing enum values (e.g. "income")."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda members: [member.value for member in members],
    )
