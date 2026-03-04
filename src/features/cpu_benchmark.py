"""CPU model → PassMark benchmark score lookup with fuzzy matching.

Covers common Intel Core i3/i5/i7/i9 CPUs (6th–12th gen) that appear
in Japanese used-PC listings scraped from Rakuten and PC Koubou.
"""

from __future__ import annotations

import logging
import re

from rapidfuzz import process

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lookup table: normalised CPU model string → PassMark score (approximate)
# Strings use the canonical "Core iN-XXXXU/H" form, stripped of vendor prefix.
# ---------------------------------------------------------------------------
BENCHMARK_SCORES: dict[str, int] = {
    # ── 6th gen (Skylake) ──────────────────────────────────────────────────
    "Core i3-6100U": 3150,
    "Core i5-6200U": 4200,
    "Core i5-6300U": 4500,
    "Core i7-6500U": 5000,
    "Core i7-6600U": 5400,
    "Core i7-6700HQ": 8200,
    # ── 7th gen (Kaby Lake) ────────────────────────────────────────────────
    "Core i3-7100U": 3400,
    "Core i5-7200U": 4800,
    "Core i5-7300U": 5100,
    "Core i7-7500U": 5600,
    "Core i7-7600U": 5900,
    "Core i7-7700HQ": 9200,
    # ── 8th gen (Whiskey/Coffee Lake) ─────────────────────────────────────
    "Core i3-8130U": 4200,
    "Core i3-8145U": 4300,
    "Core i5-8250U": 7000,
    "Core i5-8265U": 7200,
    "Core i5-8350U": 7500,
    "Core i7-8550U": 7700,
    "Core i7-8650U": 8000,
    "Core i7-8565U": 8200,
    "Core i7-8750H": 12500,
    # ── 9th gen ────────────────────────────────────────────────────────────
    "Core i5-9300H": 9500,
    "Core i7-9750H": 13000,
    # ── 10th gen (Comet/Ice Lake) ─────────────────────────────────────────
    "Core i3-10110U": 4500,
    "Core i3-10210U": 5000,
    "Core i5-10210U": 7800,
    "Core i5-10310U": 8000,
    "Core i5-10510U": 8300,
    "Core i7-10510U": 9000,
    "Core i7-10610U": 9400,
    "Core i7-10710U": 10200,
    "Core i5-1035G1": 8600,
    "Core i7-1065G7": 10500,
    # ── 11th gen (Tiger Lake) ─────────────────────────────────────────────
    "Core i3-1115G4": 7500,
    "Core i5-1135G7": 11500,
    "Core i7-1165G7": 13500,
    "Core i7-1185G7": 15000,
    # ── 12th gen (Alder Lake) ─────────────────────────────────────────────
    "Core i3-1215U": 9000,
    "Core i5-1235U": 14000,
    "Core i5-1240P": 18000,
    "Core i7-1255U": 16500,
    "Core i7-1260P": 20000,
    "Core i7-1280P": 22000,
    # ── Celeron / Pentium (budget) ────────────────────────────────────────
    "Celeron 3865U": 1500,
    "Celeron 4205U": 1600,
    "Pentium Silver N5000": 2200,
    "Pentium Gold 4415U": 2800,
    # ── AMD Ryzen (common in used listings) ───────────────────────────────
    "Ryzen 3 3200U": 5000,
    "Ryzen 5 3500U": 7800,
    "Ryzen 7 3700U": 9500,
    "Ryzen 5 4500U": 11000,
    "Ryzen 7 4700U": 14500,
    "Ryzen 5 5500U": 13000,
    "Ryzen 7 5700U": 16000,
}

# Pre-built list of keys for rapidfuzz matching
_CPU_KEYS: list[str] = list(BENCHMARK_SCORES.keys())

# Strip common vendor prefixes before fuzzy matching
_PREFIX_RE = re.compile(
    r"(?:intel\s*|インテル\s*|AMD\s*|amd\s*|cpu[:\s]*)",
    re.IGNORECASE,
)


def _normalise(cpu_str: str) -> str:
    """Strip vendor prefixes and collapse whitespace."""
    return _PREFIX_RE.sub("", cpu_str).strip()


def get_benchmark_score(cpu_str: str | None, min_score: int = 72) -> float | None:
    """Return a PassMark benchmark score for a CPU string using fuzzy matching.

    Args:
        cpu_str: Raw CPU string from ``products.cpu`` column (e.g. "Intel Core i5-8250U").
        min_score: Minimum rapidfuzz WRatio score (0–100) required to accept a match.
                   72 is a conservative threshold that avoids false positives across
                   different CPU generations.

    Returns:
        PassMark score as float, or ``None`` if no confident match is found.
    """
    if not cpu_str:
        return None

    normalised = _normalise(cpu_str)
    if not normalised:
        return None

    result = process.extractOne(normalised, _CPU_KEYS, score_cutoff=min_score)
    if result is None:
        logger.debug("No benchmark match for CPU: %r (normalised: %r)", cpu_str, normalised)
        return None

    matched_key, score, _ = result
    logger.debug("CPU %r → %r (score=%d, PassMark=%d)", cpu_str, matched_key, score, BENCHMARK_SCORES[matched_key])
    return float(BENCHMARK_SCORES[matched_key])
