"""Unit tests for LightGBMPriceModel and evaluation metrics.

All tests use synthetic local data — no Supabase calls.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from src.models.evaluation import mae, mape, r2, rmse
from src.models.price_model import LightGBMPriceModel


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_sample_df(n: int = 30) -> tuple[pl.DataFrame, pl.Series]:
    """Build a synthetic DataFrame that mimics raw Supabase products columns."""
    rng = np.random.default_rng(42)

    brands = ["Lenovo", "Dell", "HP", "Fujitsu", "Panasonic"]
    cpu_gens = ["8", "10", "12", "11", "7"]
    memories = ["8GB", "16GB", "32GB", "4GB", "16GB"]
    ssds = ["256GB", "512GB", "1TB", "128GB", "512GB"]
    hdds = [None, "500GB", None, "1TB", None]
    displays = ["14.0インチ", "15.6インチ", "13.3インチ", "12.5インチ", "14.0インチ"]
    oses = ["Windows 10 Pro 64bit", "Windows 11 Pro", None, "Windows 10 Home", "Windows 11 Pro"]
    sources = ["rakuten", "pckoubou", "rakuten", "rakuten", "pckoubou"]

    idx = [i % 5 for i in range(n)]
    df = pl.DataFrame(
        {
            "brand": [brands[i] for i in idx],
            "cpu_gen": [cpu_gens[i] for i in idx],
            "memory": [memories[i] for i in idx],
            "ssd": [ssds[i] for i in idx],
            "hdd": [hdds[i] for i in idx],
            "display_size": [displays[i] for i in idx],
            "os": [oses[i] for i in idx],
            "source": [sources[i] for i in idx],
        }
    )

    # Rough price function: higher RAM + SSD + CPU gen → higher price
    base = rng.integers(15_000, 50_000, size=n)
    prices = pl.Series("price", base.tolist())
    return df, prices


# ── Test: _parse_features basic ───────────────────────────────────────────────


def test_parse_features_basic() -> None:
    """String inputs produce correct numeric columns with expected values."""
    df, _ = _make_sample_df(5)
    parsed = LightGBMPriceModel._parse_features(df)

    # Shape: one row per input, exactly FEATURE_COLS columns
    assert parsed.shape == (5, len(LightGBMPriceModel.FEATURE_COLS))
    assert list(parsed.columns) == LightGBMPriceModel.FEATURE_COLS

    # Dtypes
    assert parsed["ram_gb"].dtype == pl.Int32
    assert parsed["ssd_gb"].dtype == pl.Int32
    assert parsed["hdd_gb"].dtype == pl.Int32
    assert parsed["cpu_gen"].dtype == pl.Float32
    assert parsed["display_size"].dtype == pl.Float32
    assert parsed["brand"].dtype == pl.Utf8
    assert parsed["os_clean"].dtype == pl.Utf8

    # Spot-check first row (brand=Lenovo, memory=8GB, ssd=256GB, os=Win10)
    row = parsed.row(0, named=True)
    assert row["brand"] == "Lenovo"
    assert row["ram_gb"] == 8
    assert row["ssd_gb"] == 256
    assert row["os_clean"] == "win10"
    assert row["cpu_gen"] == pytest.approx(8.0)

    # TB conversion: "1TB" → 1024
    tb_row_idx = next(i for i, v in enumerate(df["ssd"].to_list()) if v == "1TB")
    assert parsed["ssd_gb"][tb_row_idx] == 1024


# ── Test: _parse_features null handling ───────────────────────────────────────


def test_parse_features_nulls() -> None:
    """Null/missing values are handled gracefully without crashing."""
    df = pl.DataFrame(
        {
            "brand": [None, "Lenovo"],
            "cpu_gen": [None, "10"],
            "memory": [None, "8GB"],
            "ssd": [None, "256GB"],
            "hdd": [None, None],
            "display_size": [None, "15.6インチ"],
            "os": [None, None],
            "source": ["rakuten", None],
        }
    )
    parsed = LightGBMPriceModel._parse_features(df)

    assert parsed.shape == (2, len(LightGBMPriceModel.FEATURE_COLS))

    null_row = parsed.row(0, named=True)
    assert null_row["brand"] == "unknown"       # null → "unknown"
    assert null_row["ram_gb"] == 0              # null → 0
    assert null_row["hdd_gb"] == 0              # null → 0
    assert null_row["cpu_gen"] == pytest.approx(-1.0)      # null → -1
    assert null_row["display_size"] == pytest.approx(-1.0) # null → -1
    assert null_row["os_clean"] == "other"      # null → "other"
    assert null_row["source"] == "rakuten"

    # Second row: source is null → "unknown"
    assert parsed.row(1, named=True)["source"] == "unknown"


# ── Test: fit/predict shape ────────────────────────────────────────────────────


def test_fit_predict_shape() -> None:
    """predict() returns a Series with the same length as the input."""
    df, y = _make_sample_df(30)
    model = LightGBMPriceModel()
    model.fit(df, y)

    preds = model.predict(df)

    assert isinstance(preds, pl.Series)
    assert len(preds) == len(y)
    assert preds.name == "predicted_price"
    assert preds.dtype == pl.Int64
    # Sanity: predictions are positive prices
    assert preds.min() > 0  # type: ignore[operator]


# ── Test: save / load roundtrip ────────────────────────────────────────────────


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """Saved model, when reloaded, produces identical predictions."""
    df, y = _make_sample_df(30)
    model = LightGBMPriceModel()
    model.fit(df, y)

    original_preds = model.predict(df)

    path = tmp_path / "test_model.joblib"
    model.save(path)
    assert path.exists()

    loaded = LightGBMPriceModel.load(path)
    assert isinstance(loaded, LightGBMPriceModel)

    loaded_preds = loaded.predict(df)
    assert (original_preds == loaded_preds).all()


# ── Test: evaluation metrics ──────────────────────────────────────────────────


def test_evaluation_metrics() -> None:
    """MAE, RMSE, MAPE, R² return correct types and expected ranges."""
    y_true = pl.Series([10_000, 20_000, 30_000, 40_000])
    y_pred = pl.Series([12_000, 18_000, 31_000, 39_000])
    # Errors:  2000   2000   1000   1000

    mae_val = mae(y_true, y_pred)
    rmse_val = rmse(y_true, y_pred)
    mape_val = mape(y_true, y_pred)
    r2_val = r2(y_true, y_pred)

    # All return float
    assert isinstance(mae_val, float)
    assert isinstance(rmse_val, float)
    assert isinstance(mape_val, float)
    assert isinstance(r2_val, float)

    # Non-negative error metrics
    assert mae_val >= 0.0
    assert rmse_val >= 0.0
    assert mape_val >= 0.0
    assert r2_val <= 1.0

    # Exact values
    assert mae_val == pytest.approx(1500.0)
    # RMSE = sqrt((2000²+2000²+1000²+1000²)/4) = sqrt(2500000) ≈ 1581.14
    assert rmse_val == pytest.approx(1581.139, rel=1e-3)
    # MAPE = mean(20%, 10%, 3.33%, 2.5%) ≈ 8.958%
    assert mape_val == pytest.approx(8.958, rel=1e-2)

    # Perfect predictions → R²=1
    assert r2(y_true, y_true) == pytest.approx(1.0)
    # R² for our preds should be high (close predictions)
    assert r2_val > 0.9
