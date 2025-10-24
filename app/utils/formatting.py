"""Utility helpers for formatting values for display."""
from __future__ import annotations

from datetime import date
from typing import Iterable


def format_int(value: int | None) -> str:
    """Return a string with thousands separator for ``value``.

    Args:
        value: Integer value to format.

    Returns:
        Formatted string, defaulting to ``"0"`` when ``None`` is provided.
    """

    if value is None:
        return "0"
    return f"{value:,}"


def format_date_range(start: date, end: date) -> str:
    """Return a human readable representation of a date range."""

    return f"{start:%Y-%m-%d} – {end:%Y-%m-%d}"


def top_n(items: Iterable[tuple[str, int]], limit: int = 3) -> list[tuple[str, int]]:
    """Return the ``limit`` highest values sorted descending."""

    return sorted(items, key=lambda item: item[1], reverse=True)[:limit]

