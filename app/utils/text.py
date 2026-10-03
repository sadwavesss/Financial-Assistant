"""Text normalization used for keyword matching and duplicate detection."""

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Lower-case, replace "ё" with "е" and collapse whitespace.

    Example: "  Рублёвский  N1" -> "рублевский n1".
    """
    return _WHITESPACE.sub(" ", value.lower().replace("ё", "е")).strip()
