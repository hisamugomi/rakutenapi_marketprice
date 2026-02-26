"""Tests for src/scrapers/rakuten_filter.py.

Run with: uv run pytest tests/test_scrapers/test_rakuten_filter.py -v
"""

from __future__ import annotations

import time

import polars as pl
import pytest

from src.scrapers.rakuten_filter import filter_rakuten_computers

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_df(name: str, genre_id: str | int | None) -> pl.DataFrame:
    """Build a minimal single-row DataFrame matching the Rakuten API columns."""
    return pl.DataFrame(
        {
            "itemName": [name],
            "genreId": [genre_id],
        },
        schema={"itemName": pl.Utf8, "genreId": pl.Utf8 if isinstance(genre_id, str) else pl.Int64},
    )


def make_df_str(name: str, genre_id: str | None) -> pl.DataFrame:
    """Build a single-row DataFrame with genreId as Utf8 (or null)."""
    return pl.DataFrame({"itemName": [name], "genreId": [genre_id]})


# ── Basic keep / reject ───────────────────────────────────────────────────────


def test_keeps_computer_genre_clean() -> None:
    """Computer genreId with no noise keywords → kept, is_uncertain=False."""
    df = make_df_str("ThinkPad X260 中古 ノートPC Windows 10", "100040")
    result = filter_rakuten_computers(df)
    assert len(result) == 1
    assert result["is_uncertain"][0] is False


def test_keeps_unknown_genre_clean() -> None:
    """Unknown genreId=0 with computer keyword, no noise → kept, is_uncertain=False."""
    df = make_df_str("ThinkPad L470 Core i5 SSD256GB", "0")
    result = filter_rakuten_computers(df)
    assert len(result) == 1
    assert result["is_uncertain"][0] is False


def test_rejects_noise_genre() -> None:
    """Items in NOISE_GENRE_IDS are always rejected."""
    df = make_df_str("ThinkPad バッテリー 交換用", "552420")
    result = filter_rakuten_computers(df)
    assert len(result) == 0


def test_rejects_noise_keyword_in_computer_genre() -> None:
    """Computer genreId but name contains a noise keyword → rejected (mislabeled accessory)."""
    df = make_df_str("ノートPC用 バッグ ケース 15インチ対応", "100040")
    result = filter_rakuten_computers(df)
    assert len(result) == 0


def test_rejects_noise_only_unknown_genre() -> None:
    """Unknown genreId, noise keyword present, no computer keyword → rejected."""
    df = make_df_str("ACアダプター 充電器 65W 汎用", "0")
    result = filter_rakuten_computers(df)
    assert len(result) == 0


def test_keeps_uncertain_mixed_signals() -> None:
    """Unknown genreId, BOTH noise and computer keywords → kept with is_uncertain=True."""
    df = make_df_str("ThinkPad L580 ACアダプター 充電器 純正品", "0")
    result = filter_rakuten_computers(df)
    assert len(result) == 1
    assert result["is_uncertain"][0] is True


# ── Edge cases ────────────────────────────────────────────────────────────────


def test_handles_null_genre() -> None:
    """None genreId treated as unknown → if no noise keyword, kept clean."""
    df = pl.DataFrame({"itemName": ["ThinkPad E490 ノートパソコン"], "genreId": [None]})
    result = filter_rakuten_computers(df)
    assert len(result) == 1
    assert result["is_uncertain"][0] is False


def test_handles_integer_genre() -> None:
    """genreId stored as Int64 (not Utf8) should be normalised and kept."""
    df = pl.DataFrame(
        {"itemName": ["Let's note CF-SZ6 Core i5"], "genreId": [100040]},
        schema={"itemName": pl.Utf8, "genreId": pl.Int64},
    )
    result = filter_rakuten_computers(df)
    assert len(result) == 1
    assert result["is_uncertain"][0] is False


def test_empty_dataframe() -> None:
    """Empty DataFrame is returned unchanged (no crash)."""
    df = pl.DataFrame(
        {"itemName": pl.Series([], dtype=pl.Utf8), "genreId": pl.Series([], dtype=pl.Utf8)}
    )
    result = filter_rakuten_computers(df)
    assert len(result) == 0


# ── Parametrized keep cases ───────────────────────────────────────────────────

_KEEP_CASES: list[tuple[str, str | None, bool]] = [
    # (itemName, genreId, expected_is_uncertain)
    ("ThinkPad X280 Core i5 SSD256 Windows11", "100040", False),
    ("LIFEBOOK A576 Core i5 8GB", "100040", False),
    ("MacBook Pro 2019 16インチ", "100026", False),
    ("ノートパソコン Ryzen 5 256GB SSD 中古", "0", False),
    ("Surface Pro 7 i5-1035G4 8GB SSD256", None, False),
    # Mixed signals in unknown genre → uncertain
    ("ThinkPad X250 バッテリー 内蔵 交換済み", "0", True),
    ("Let's note CF-MX4 ACアダプター セット", "0", True),
]


@pytest.mark.parametrize("name,genre,expected_uncertain", _KEEP_CASES)
def test_full_task_spec_keep_cases(name: str, genre: str | None, expected_uncertain: bool) -> None:
    """All entries in _KEEP_CASES must survive the filter."""
    df = pl.DataFrame({"itemName": [name], "genreId": [genre]})
    result = filter_rakuten_computers(df)
    assert len(result) == 1, f"Expected keep but got reject for: {name!r} (genre={genre})"
    assert result["is_uncertain"][0] is expected_uncertain


# ── Parametrized reject cases ─────────────────────────────────────────────────

_REJECT_CASES: list[tuple[str, str]] = [
    ("ノートPC用バッグ 15.6インチ ブラック", "100040"),
    ("バッテリーパック ThinkPad 互換品", "552420"),
    ("ACアダプター 19V 汎用品 USB-C", "0"),
    ("ノートPCスタンド 折りたたみ アルミ", "552420"),
    ("充電ケーブル USB Type-C 2m", "0"),
]


@pytest.mark.parametrize("name,genre", _REJECT_CASES)
def test_full_task_spec_reject_cases(name: str, genre: str) -> None:
    """All entries in _REJECT_CASES must be removed by the filter."""
    df = pl.DataFrame({"itemName": [name], "genreId": [genre]})
    result = filter_rakuten_computers(df)
    assert len(result) == 0, f"Expected reject but got keep for: {name!r} (genre={genre})"


# ── Performance ───────────────────────────────────────────────────────────────


def test_performance_10k_rows() -> None:
    """Filter 10,000 rows in under 1 second."""
    names = [
        "ThinkPad X260 Core i5 SSD256",
        "ACアダプター 充電器 65W",
        "ノートPCバッグ 15インチ",
        "Let's note CF-SZ6 Windows 11",
        "ThinkPad バッテリー 純正 充電器",
    ]
    genres = ["100040", "0", "100040", "0", "0"]
    n = 10_000
    df = pl.DataFrame(
        {
            "itemName": [names[i % len(names)] for i in range(n)],
            "genreId": [genres[i % len(genres)] for i in range(n)],
        }
    )
    start = time.monotonic()
    result = filter_rakuten_computers(df)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"Filter took {elapsed:.2f}s for {n} rows (expected < 1s)"
    assert len(result) > 0
