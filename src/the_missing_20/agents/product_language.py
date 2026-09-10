"""Deterministic display-language boundary for model-authored product prose."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable


class ProductLanguageViolation(ValueError):
    """A model attempted to return non-English product prose."""


def english_product_text(value: object, *, field: str) -> str:
    """Accept English/Latin text and neutral symbols, reject other writing systems.

    This intentionally permits ordinary typographic punctuation, numbers, and
    Latin names such as ``café``. It is a display boundary only: human input and
    source records remain untouched, so the model can still understand a request
    written in another language.
    """

    if not isinstance(value, str) or not value.strip():
        raise ProductLanguageViolation(f"{field} must be non-empty English text")
    for character in value:
        if not character.isalpha():
            continue
        name = unicodedata.name(character, "")
        if "LATIN" not in name:
            raise ProductLanguageViolation(f"{field} must be English-only")
    return value.strip()


def english_product_texts(values: Iterable[object], *, field: str) -> tuple[str, ...]:
    """Validate every model-authored follow-up without translating or rewriting it."""

    return tuple(english_product_text(value, field=field) for value in values)
