"""Extract and normalise laptop model names from Japanese used-PC listing titles.

Usage::

    from src.features.model_extractor import extract_model

    extract_model("【中古】Lenovo ThinkPad L580 Core i5 ...")  # → "ThinkPad L580"
    extract_model("DELL LATITUDE 5300 2-in-1 ...")            # → "Latitude 5300"
    extract_model("完全に別の商品")                             # → None
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Rules: ordered list of (compiled pattern, label template).
# The first match wins — put more-specific rules before generic ones.
# group(1) of each pattern is the variable part that fills in the template.
# ---------------------------------------------------------------------------
_RULES: list[tuple[re.Pattern[str], str]] = [
    # ── Lenovo ThinkPad ─────────────────────────────────────────────────────
    # X1 two-word series must come before the generic ThinkPad rule
    (re.compile(r"ThinkPad\s+(X1\s+(?:Carbon|Yoga|Nano|Extreme))", re.IGNORECASE), "ThinkPad {}"),
    # Generic ThinkPad: L390, T14s, E480, X280, A285, etc.
    (re.compile(r"ThinkPad\s+([A-Z]\d{2,3}[a-zA-Z0-9]*)", re.IGNORECASE), "ThinkPad {}"),
    # ── Lenovo IdeaPad ──────────────────────────────────────────────────────
    (re.compile(r"IdeaPad\s+(Slim\s*\d+|[A-Z]\d{1,2})", re.IGNORECASE), "IdeaPad {}"),
    # ── Dell Latitude ───────────────────────────────────────────────────────
    # Legacy e-series (e5400, e5500) before 4-digit rule to avoid partial match
    (re.compile(r"Latitude\s+(e\d{4})", re.IGNORECASE), "Latitude {}"),
    # Modern 4-digit (5300, 5400, 5490, 5500, 5590, 5320, …)
    (re.compile(r"Latitude\s+(\d{4})", re.IGNORECASE), "Latitude {}"),
    # ── Dell Inspiron ───────────────────────────────────────────────────────
    (re.compile(r"\bInspiron\s+(\d{2,5})\b", re.IGNORECASE), "Inspiron {}"),
    # ── Dell XPS ────────────────────────────────────────────────────────────
    (re.compile(r"\bXPS\s+(\d{2})\b", re.IGNORECASE), "Dell XPS {}"),
    # ── Lenovo Legion ───────────────────────────────────────────────────────
    (re.compile(r"\bLegion\s+([A-Z0-9][\w]*\d+[\w]*)", re.IGNORECASE), "Legion {}"),
]


def _normalise(raw: str) -> str:
    """Title-case each word so results are consistent regardless of source casing.

    Examples:
        "l580"    → "L580"
        "e5400"   → "E5400"
        "x1 carbon" → "X1 Carbon"
    """
    return " ".join(word.capitalize() for word in raw.strip().split())


def extract_model(title: str) -> str | None:
    """Return a normalised model string extracted from a listing title.

    Args:
        title: Raw ``itemName`` string from a Rakuten or PC Koubou listing.

    Returns:
        A canonical model name such as ``"ThinkPad L580"`` or ``"Latitude 5300"``,
        or ``None`` if no known model pattern is found.
    """
    for pattern, template in _RULES:
        m = pattern.search(title)
        if m:
            return template.format(_normalise(m.group(1)))
    return None
