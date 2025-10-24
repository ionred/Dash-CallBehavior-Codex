"""Shared caching helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask_caching import Cache


@dataclass
class CacheKeys:
    """Centralised cache key definitions."""

    EVENT_LISTINGS: str = "event_listings"
    RAW_DATA_PREFIX: str = "raw_data:"


class CacheService:
    """Service wrapper around :class:`flask_caching.Cache`."""

    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    def get_event_listings(self) -> Any:
        return self._cache.get(CacheKeys.EVENT_LISTINGS)

    def set_event_listings(self, value: Any, timeout: int | None = None) -> None:
        self._cache.set(CacheKeys.EVENT_LISTINGS, value, timeout=timeout)

    def get_raw_data(self, event_name: str, subgroup: str) -> Any:
        return self._cache.get(self._raw_key(event_name, subgroup))

    def set_raw_data(self, event_name: str, subgroup: str, value: Any, timeout: int | None = None) -> None:
        self._cache.set(self._raw_key(event_name, subgroup), value, timeout=timeout)

    def delete_raw_data(self, event_name: str, subgroup: str) -> None:
        self._cache.delete(self._raw_key(event_name, subgroup))

    def clear_prefix(self, prefix: str) -> None:
        if hasattr(self._cache, "cache"):  # type: ignore[attr-defined]
            cache_obj = getattr(self._cache, "cache")
            if hasattr(cache_obj, "_cache"):
                keys = [key for key in cache_obj._cache.keys() if key.startswith(prefix)]
                for key in keys:
                    cache_obj.delete(key)

    def _raw_key(self, event_name: str, subgroup: str) -> str:
        return f"{CacheKeys.RAW_DATA_PREFIX}{event_name.lower()}::{subgroup.lower()}"

