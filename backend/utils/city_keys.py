"""
Helpers for per-city model paths and name matching.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional


def city_slug(name: str) -> str:
    """
    Convert city name into filesystem-safe slug.

    Example:
        "Islamabad City" -> "islamabad_city"
    """
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip()).strip("_").lower()
    return s or "unknown"


def match_trained_city(
    requested: Optional[str],
    trained_keys: Iterable[str]
) -> Optional[str]:
    """
    Case-insensitive match of requested city to trained registry keys.

    Example:
        'islamabad' -> 'Islamabad'
    """
    if not requested:
        return None

    r = str(requested).strip().lower()

    for k in trained_keys:
        if str(k).strip().lower() == r:
            return k

    return None


def resolve_city_with_fallback(
    requested: Optional[str],
    trained_keys: Iterable[str],
    fallback: str = "Islamabad",
    logger=None
) -> str:
    """
    Resolve city name with fallback if not found.

    This is where fallback logic belongs (NOT inside match_trained_city).

    Args:
        requested: User input city
        trained_keys: Available trained cities
        fallback: Default city if not found
        logger: Optional logger

    Returns:
        Valid city key
    """
    key = match_trained_city(requested, trained_keys)

    if key is None:
        if logger:
            logger.warning(
                f"Unknown city '{requested}', falling back to '{fallback}'"
            )
        return fallback

    return key


def build_city_registry_payload(
    cities: Dict[str, Dict],
    threshold_percentile: float,
) -> Dict:
    """
    Build registry metadata for per-city models.
    """
    return {
        "version": 2,
        "mode": "per_city",
        "threshold_percentile": float(threshold_percentile),
        "cities": cities,
    }