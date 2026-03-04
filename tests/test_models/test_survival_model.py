"""Tests for SurvivalModel — uses synthetic listing data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from src.models.survival_model import SurvivalModel


def make_listing_df(n: int = 50) -> pl.DataFrame:
    """Synthetic listings with first_seen_at, last_seen_at, is_active.

    Half the rows are inactive (completed sales), half are still active.
    Durations range from 1 to 90 days.
    """
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first_seen = [base for _ in range(n)]
    last_seen = [base + timedelta(days=1 + (i % 90)) for i in range(n)]
    is_active = [i % 2 == 1 for i in range(n)]  # alternating

    return pl.DataFrame(
        {
            "first_seen_at": pl.Series(first_seen).cast(pl.Datetime("us", "UTC")),
            "last_seen_at": pl.Series(last_seen).cast(pl.Datetime("us", "UTC")),
            "is_active": is_active,
        }
    )


def test_fit_succeeds_with_valid_data() -> None:
    """fit() completes without raising on valid data."""
    df = make_listing_df(50)
    model = SurvivalModel()
    result = model.fit(df)
    assert result is model  # returns self
    assert model.mu_ is not None
    assert model.sigma_ is not None


def test_predict_median_time_positive() -> None:
    """predict_median_time() returns a positive number of days."""
    df = make_listing_df(50)
    model = SurvivalModel().fit(df)
    median = model.predict_median_time()
    assert isinstance(median, float)
    assert median > 0.0


def test_survival_at_30_days_between_0_and_1() -> None:
    """predict_survival_at(30) returns a probability in [0, 1]."""
    df = make_listing_df(50)
    model = SurvivalModel().fit(df)
    prob = model.predict_survival_at(days=30)
    assert isinstance(prob, float)
    assert 0.0 <= prob <= 1.0


def test_survival_at_0_days_is_near_1() -> None:
    """P(survival at day 0) should be ≈ 1.0 (just listed, not yet sold)."""
    df = make_listing_df(50)
    model = SurvivalModel().fit(df)
    assert model.predict_survival_at(days=0) > 0.99


def test_price_sensitivity_below_median_lt_1() -> None:
    """price below market_median → multiplier < 1.0 (faster sale)."""
    model = SurvivalModel()
    multiplier = model.price_sensitivity(price=30_000.0, market_median=50_000.0)
    assert multiplier < 1.0


def test_price_sensitivity_above_median_gt_1() -> None:
    """price above market_median → multiplier > 1.0 (slower sale)."""
    model = SurvivalModel()
    multiplier = model.price_sensitivity(price=80_000.0, market_median=50_000.0)
    assert multiplier > 1.0


def test_price_sensitivity_at_median_is_1() -> None:
    """price equal to market_median → multiplier = 1.0."""
    model = SurvivalModel()
    multiplier = model.price_sensitivity(price=50_000.0, market_median=50_000.0)
    assert multiplier == pytest.approx(1.0)


def test_fit_raises_if_no_completed_sales() -> None:
    """fit() raises ValueError when all rows have is_active=True."""
    df = make_listing_df(20).with_columns(pl.lit(True).alias("is_active"))
    model = SurvivalModel()
    with pytest.raises(ValueError, match="completed sales"):
        model.fit(df)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    """Saved model reloads and produces identical predictions."""
    df = make_listing_df(50)
    model = SurvivalModel().fit(df)
    path = tmp_path / "survival_model.joblib"
    model.save(path)
    assert path.exists()
    loaded = SurvivalModel.load(path)
    assert isinstance(loaded, SurvivalModel)
    assert loaded.mu_ == pytest.approx(model.mu_)
    assert loaded.sigma_ == pytest.approx(model.sigma_)
