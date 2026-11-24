"""Russian-style number formatting shared by services and templates."""

from decimal import Decimal


def format_money(value: Decimal | None) -> str:
    """Decimal("1234.5") -> "1 234,50" (non-breaking thousands separator, decimal comma)."""
    if value is None:
        return ""
    return f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
