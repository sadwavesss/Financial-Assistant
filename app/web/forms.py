"""Turning HTML form data into input suitable for validation by Pydantic schemas."""

from collections.abc import Mapping

DECIMAL_FIELDS = {"amount", "manual_rate"}


def clean_form(data: Mapping[str, str]) -> dict[str, str]:
    """Drop empty fields (so defaults apply) and accept a comma as the decimal separator."""
    cleaned = {}
    for key, value in data.items():
        value = value.strip()
        if not value:
            continue
        cleaned[key] = value.replace(" ", "").replace(",", ".") if key in DECIMAL_FIELDS else value
    return cleaned
