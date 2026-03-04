"""Tests for FeatureBuilder."""

from __future__ import annotations

import polars as pl
import pytest

from src.features.builder import FeatureBuilder


def _make_raw_df(**overrides) -> pl.DataFrame:
    """Create a minimal raw products-like DataFrame for testing."""
    defaults = {
        "brand": ["Lenovo", "Dell", None],
        "cpu_gen": ["8", "10", "12"],
        "cpu": ["Core i5-8250U", "Core i7-10510U", "Core i5-1235U"],
        "memory": ["16GB", "8GB", None],
        "ssd": ["512GB", "1TB", "256GB"],
        "hdd": [None, "500GB", None],
        "display_size": ["14.0インチ", "15.6インチ", "13.3インチ"],
        "os": ["Windows 10 Pro 64bit", "Windows 11 Pro", None],
        "source": ["rakuten", "pckoubou", "rakuten"],
    }
    defaults.update(overrides)
    return pl.DataFrame(defaults)


def test_build_returns_expected_columns() -> None:
    """build() output contains all declared FEATURE_COLS."""
    builder = FeatureBuilder()
    df = _make_raw_df()
    result = builder.build(df)

    for col in builder.FEATURE_COLS:
        assert col in result.columns, f"Missing column: {col}"


def test_build_handles_null_memory() -> None:
    """Null memory value → ram_gb = 0."""
    builder = FeatureBuilder()
    df = _make_raw_df(memory=[None, "8GB", "16GB"])
    result = builder.build(df)
    assert result["ram_gb"][0] == 0


def test_build_handles_tb_storage() -> None:
    """'1TB' SSD → ssd_gb = 1024."""
    builder = FeatureBuilder()
    df = _make_raw_df(ssd=["1TB", "512GB", "256GB"])
    result = builder.build(df)
    assert result["ssd_gb"][0] == 1024


def test_build_os_normalization() -> None:
    """'Windows 10 Pro' → os_clean = 'win10'."""
    builder = FeatureBuilder()
    df = _make_raw_df(os=["Windows 10 Pro 64bit", "Windows 11 Home", "Windows 7"])
    result = builder.build(df)
    assert result["os_clean"][0] == "win10"
    assert result["os_clean"][1] == "win11"
    assert result["os_clean"][2] == "win7"


def test_build_os_null_becomes_other() -> None:
    """Null OS → os_clean = 'other'."""
    builder = FeatureBuilder()
    df = _make_raw_df(os=[None, None, None])
    result = builder.build(df)
    assert all(v == "other" for v in result["os_clean"].to_list())


def test_build_unknown_cpu_does_not_crash() -> None:
    """Unknown CPU string → cpu_benchmark is None/null, no exception raised."""
    builder = FeatureBuilder()
    df = _make_raw_df(cpu=["completely unknown cpu xyz", None, "mystery chip"])
    result = builder.build(df)
    assert "cpu_benchmark" in result.columns
    # All should be null (no match found)
    assert result["cpu_benchmark"].null_count() == len(result)


def test_build_known_cpu_returns_score() -> None:
    """Known CPU string → cpu_benchmark is a positive float."""
    builder = FeatureBuilder()
    df = _make_raw_df(cpu=["Core i5-8250U", "Core i7-10510U", "Core i5-8250U"])
    result = builder.build(df)
    scores = result["cpu_benchmark"].drop_nulls()
    assert len(scores) > 0
    assert all(s > 0 for s in scores.to_list())


def test_build_missing_columns_filled_with_defaults() -> None:
    """DataFrame with only 'brand' column produces all FEATURE_COLS without crash."""
    builder = FeatureBuilder()
    df = pl.DataFrame({"brand": ["Lenovo", "Dell"]})
    result = builder.build(df)
    # Should not raise; all output cols that were producible should be present
    assert "brand" in result.columns
    assert "ram_gb" in result.columns
    assert result["ram_gb"].to_list() == [0, 0]


def test_build_hdd_extraction() -> None:
    """HDD column correctly parsed: '500GB' → 500, None → 0."""
    builder = FeatureBuilder()
    df = _make_raw_df(hdd=["500GB", None, "2TB"])
    result = builder.build(df)
    assert result["hdd_gb"][0] == 500
    assert result["hdd_gb"][1] == 0
    assert result["hdd_gb"][2] == 2048
