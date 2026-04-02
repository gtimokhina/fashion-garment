"""
Helpers for image ``metadata`` JSON: each structured attribute may be either a legacy
plain string or ``{"value": str, "confidence": float}``.

**Heuristic confidence** (when the model omits it or legacy rows only have a string):

- Empty ``value`` → confidence **0.0**
- Substrings suggesting uncertainty (``unknown``, ``unclear``, ``not visible``, ``n/a``, etc.)
  → **0.35**
- Otherwise → **0.50 + min(0.45, 0.04 × word_count)** (capped at **0.95**): slightly higher for
  longer phrases, as a weak proxy for “more grounded” text (not a calibrated probability).
"""

from __future__ import annotations

import re
from typing import Any

_UNCERTAINTY_HINTS = re.compile(
    r"\b(unknown|unclear|not\s+visible|cannot\s+(see|determine)|n/?a|none\s+visible)\b",
    re.I,
)


def heuristic_confidence_for_value(value: str) -> float:
    """
    Estimate confidence in [0, 1] when the model does not return one.
    See module docstring for the documented rules.
    """
    v = (value or "").strip()
    if not v:
        return 0.0
    if _UNCERTAINTY_HINTS.search(v):
        return 0.35
    words = len(v.split())
    return min(0.95, 0.50 + min(0.45, 0.04 * min(words, 12)))


def meta_field_value(raw: Any) -> str:
    """Extract display/filter value from a metadata field (legacy string or dict)."""
    if raw is None:
        return ""
    if isinstance(raw, dict):
        inner = raw.get("value")
        if inner is None:
            return ""
        return str(inner).strip()
    return str(raw).strip()


def meta_field_confidence(raw: Any) -> float | None:
    """Return confidence if present and numeric; else None (caller may use heuristic on value)."""
    if raw is None or isinstance(raw, str):
        return None
    if isinstance(raw, dict):
        c = raw.get("confidence")
        if c is None:
            return None
        try:
            return max(0.0, min(1.0, float(c)))
        except (TypeError, ValueError):
            return None
    return None


def meta_field_value_and_confidence(raw: Any) -> tuple[str, float]:
    """Value string and confidence (heuristic if missing)."""
    val = meta_field_value(raw)
    mc = meta_field_confidence(raw)
    if mc is not None:
        return val, mc
    return val, heuristic_confidence_for_value(val)
