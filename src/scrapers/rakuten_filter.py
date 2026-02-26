"""Two-layer noise filter for Rakuten Ichiba computer listings.

Algorithm
---------
1. Items in NOISE_GENRE_IDS          → always rejected
2. Items in COMPUTER_GENRE_IDS:
   - name contains a noise keyword   → rejected  (mislabelled accessory)
   - otherwise                       → kept       (is_uncertain=False)
3. Items in unknown / unspecified genre (genreId = 0 or null):
   - noise keyword AND computer keyword → kept    (is_uncertain=True)
   - noise keyword, no computer keyword → rejected
   - no noise keyword                   → kept    (is_uncertain=False)

Usage
-----
>>> from src.scrapers.rakuten_filter import filter_rakuten_computers
>>> clean = filter_rakuten_computers(raw_df)
"""

from __future__ import annotations

import logging
import re
from typing import Final

import polars as pl

logger = logging.getLogger(__name__)

# ── Genre ID lists ─────────────────────────────────────────────────────────────

COMPUTER_GENRE_IDS: Final[frozenset[str]] = frozenset({"100040", "100026"})
"""Rakuten genre IDs that reliably map to computers/laptops/desktops."""

NOISE_GENRE_IDS: Final[frozenset[str]] = frozenset({"552420"})
"""Rakuten genre IDs that are exclusively accessories (batteries, bags, etc.)."""

# ── Keyword lists ──────────────────────────────────────────────────────────────

NOISE_KEYWORDS: Final[tuple[str, ...]] = (
    # Power / charging accessories
    # Note: bare "バッテリー" is intentionally omitted — "バッテリー良好" / "バッテリー内蔵"
    # are standard used-PC quality descriptors, not accessory keywords.
    # Use specific compound forms instead.
    "バッテリーパック",
    "バッテリー交換",
    "純正バッテリー",
    "交換用バッテリー",
    "互換バッテリー",
    "アダプター",
    "アダプタ",
    "充電器",
    "ACアダプター",
    "ACアダプタ",
    "電源アダプター",
    "電源アダプタ",
    "電源ケーブル",
    # Data / display cables
    "ケーブル",
    # Carrying accessories
    "バッグ",
    "ケース",
    # Peripherals / audio
    "マウス",
    "キーボード",
    "イヤホン",
    "ヘッドホン",
    "ヘッドフォン",
    # Cooling / desk accessories
    "冷却",
    "クーラー",
    "スタンド",
    # Docking
    "ドッキング",
)
"""Keywords that identify accessories and non-computer items."""

COMPUTER_KEYWORDS: Final[tuple[str, ...]] = (
    # PC brand / model lines
    "ThinkPad",
    "レッツノート",
    "Let's note",
    "VAIO",
    "LIFEBOOK",
    "dynabook",
    "EliteBook",
    "ProBook",
    "Latitude",
    "Inspiron",
    "XPS",
    "Surface",
    "MacBook",
    "VivoBook",
    "ZenBook",
    "IdeaPad",
    "Pavilion",
    "MateBook",
    # OS names
    "Windows",
    "macOS",
    "Linux",
    # CPU families
    "Core i",
    "Ryzen",
    "Celeron",
    "Pentium",
    "Xeon",
    # Generic PC type words (Japanese)
    "ノートパソコン",
    "ノートPC",
    "デスクトップ",
    "ラップトップ",
    # Generic PC type words (Latin)
    "laptop",
    "notebook",
    "desktop",
)
"""Keywords that clearly identify a computer listing."""

# ── Compiled regex patterns ────────────────────────────────────────────────────

_NOISE_RE: Final[str] = "(?i)(?:" + "|".join(re.escape(kw) for kw in NOISE_KEYWORDS) + ")"
_COMPUTER_RE: Final[str] = "(?i)(?:" + "|".join(re.escape(kw) for kw in COMPUTER_KEYWORDS) + ")"

# ── Public API ─────────────────────────────────────────────────────────────────


def filter_rakuten_computers(df: pl.DataFrame) -> pl.DataFrame:
    """Remove non-computer listings from a Rakuten API result DataFrame.

    Args:
        df: DataFrame that must contain at least the columns ``itemName``
            (Utf8) and ``genreId`` (Utf8 or Int64).  Additional columns are
            preserved unchanged.

    Returns:
        Filtered DataFrame with an added boolean column ``is_uncertain``.
        ``is_uncertain=True`` means the item has *both* computer and noise
        keywords in an unknown genre — it may be a computer accessory bundle
        or a mislabelled listing.  The Streamlit dashboard uses this flag to
        highlight rows for manual review.

    Notes:
        Temporary work columns (prefixed ``_``) are dropped before returning.
    """
    if df.is_empty():
        return df

    # ── Step 1: normalise genreId to a stripped Utf8 string ───────────────────
    genre_norm = pl.col("genreId").cast(pl.Utf8).fill_null("0").str.strip_chars()

    df = df.with_columns(
        [
            genre_norm.alias("_genre_str"),
            pl.col("itemName").str.contains(_NOISE_RE).alias("_has_noise"),
            pl.col("itemName").str.contains(_COMPUTER_RE).alias("_has_computer"),
        ]
    )

    # ── Step 2: build Boolean mask expressions ────────────────────────────────
    in_noise_genre = pl.col("_genre_str").is_in(list(NOISE_GENRE_IDS))
    in_computer_genre = pl.col("_genre_str").is_in(list(COMPUTER_GENRE_IDS))
    in_unknown_genre = ~in_noise_genre & ~in_computer_genre

    # Rule 2: known computer genre, no noise keyword
    keep_computer_genre = in_computer_genre & ~pl.col("_has_noise")

    # Rule 3a: unknown genre, both signals present (uncertain)
    keep_uncertain = in_unknown_genre & pl.col("_has_noise") & pl.col("_has_computer")

    # Rule 3c: unknown genre, no noise keyword (clean unknown)
    keep_clean_unknown = in_unknown_genre & ~pl.col("_has_noise")

    keep_mask = keep_computer_genre | keep_uncertain | keep_clean_unknown

    # ── Step 3: log stats ─────────────────────────────────────────────────────
    stats = df.select(
        [
            pl.len().alias("total"),
            in_noise_genre.sum().alias("noise_genre_rejected"),
            (in_computer_genre & pl.col("_has_noise")).sum().alias("keyword_rejected"),
            keep_uncertain.sum().alias("uncertain_kept"),
            (keep_computer_genre | keep_clean_unknown).sum().alias("clean_kept"),
        ]
    ).row(0, named=True)

    logger.info(
        "rakuten_filter results",
        extra={
            "total": stats["total"],
            "noise_genre_rejected": stats["noise_genre_rejected"],
            "keyword_rejected": stats["keyword_rejected"],
            "uncertain_kept": stats["uncertain_kept"],
            "clean_kept": stats["clean_kept"],
        },
    )

    # ── Step 4: filter and annotate ───────────────────────────────────────────
    _temp = ["_genre_str", "_has_noise", "_has_computer"]

    return (
        df.filter(keep_mask)
        .with_columns(
            (in_unknown_genre & pl.col("_has_noise") & pl.col("_has_computer")).alias(
                "is_uncertain"
            )
        )
        .drop(_temp)
    )
