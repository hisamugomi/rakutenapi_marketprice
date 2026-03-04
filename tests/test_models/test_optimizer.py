"""Tests for LGBMOptimizer — uses tiny synthetic data for speed."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from src.models.optimizer import LGBMOptimizer
from src.models.price_model import LightGBMPriceModel


def make_synthetic_data(n: int = 80) -> tuple[pl.DataFrame, pl.Series]:
    """Create minimal synthetic training data with the same schema as real data."""
    rng = np.random.default_rng(0)
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
    prices = pl.Series("price", rng.integers(15_000, 80_000, size=n).tolist())
    return df, prices


def test_optimize_returns_dict_with_expected_keys() -> None:
    """optimize() returns a dict containing all tuned hyperparameter keys."""
    X, y = make_synthetic_data(60)
    optimizer = LGBMOptimizer(n_trials=2, cv_folds=2, random_seed=0)
    result = optimizer.optimize(X, y)

    expected_keys = {
        "num_leaves",
        "learning_rate",
        "n_estimators",
        "colsample_bytree",
        "subsample",
        "min_child_samples",
    }
    assert isinstance(result, dict)
    assert expected_keys.issubset(result.keys())


def test_get_best_model_is_lgbm_price_model() -> None:
    """get_best_model() returns a LightGBMPriceModel instance."""
    X, y = make_synthetic_data(60)
    optimizer = LGBMOptimizer(n_trials=2, cv_folds=2, random_seed=0)
    optimizer.optimize(X, y)
    model = optimizer.get_best_model()
    assert isinstance(model, LightGBMPriceModel)


def test_optimizer_can_fit_and_predict() -> None:
    """Full flow: optimize → get_best_model → fit → predict without crashing."""
    X, y = make_synthetic_data(60)
    optimizer = LGBMOptimizer(n_trials=2, cv_folds=2, random_seed=0)
    optimizer.optimize(X, y)
    model = optimizer.get_best_model()
    model.fit(X, y)
    preds = model.predict(X)
    assert isinstance(preds, pl.Series)
    assert len(preds) == len(y)
    assert preds.dtype == pl.Int64


def test_get_best_model_raises_before_optimize() -> None:
    """get_best_model() raises RuntimeError if optimize() was never called."""
    optimizer = LGBMOptimizer()
    with pytest.raises(RuntimeError, match="optimize"):
        optimizer.get_best_model()
