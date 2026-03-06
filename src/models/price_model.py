"""LightGBM price regressor for used PC listings.

Uses a sklearn Pipeline internally:
    _FeatureParser → _CatEncoder → LGBMRegressor

This ensures no data leakage between steps, and the full pipeline is
serialisable as a single joblib artifact.

Feature parsing uses native Polars expressions (no Python UDFs) for
maximum performance.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import polars as pl
from lightgbm import LGBMRegressor
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.utils.validation import check_is_fitted

logger = logging.getLogger(__name__)

# ── Constants shared by transformers and the model class ──────────────────────

_FEATURE_COLS: list[str] = [
    "brand",
    "cpu_gen",
    "ram_gb",
    "ssd_gb",
    "hdd_gb",
    "display_size",
    "os_clean",
    "source",
]
_CAT_COLS: list[str] = ["brand", "os_clean", "source"]


# ── Native Polars expression helpers ─────────────────────────────────────────


def _storage_expr(col: str) -> pl.Expr:
    """Polars expression: "512GB" → 512, "1TB" → 1024, null → 0.

    Casts to Utf8 first so all-null columns (inferred as Null dtype) are handled safely.
    """
    s = pl.col(col).cast(pl.Utf8)
    return (
        pl.when(s.str.to_uppercase().str.contains("TB", literal=True))
        .then(s.str.extract(r"(\d+)", 1).cast(pl.Int32) * 1024)
        .otherwise(s.str.extract(r"(\d+)", 1).cast(pl.Int32))
        .fill_null(0)
    )


def _os_clean_expr() -> pl.Expr:
    """Polars expression: bucket OS strings into win7/win8/win10/win11/other."""
    s = pl.col("os").cast(pl.Utf8)
    return (
        pl.when(s.str.contains("11", literal=True))
        .then(pl.lit("win11"))
        .when(s.str.contains("10", literal=True))
        .then(pl.lit("win10"))
        .when(s.str.contains("8", literal=True))
        .then(pl.lit("win8"))
        .when(s.str.contains("7", literal=True))
        .then(pl.lit("win7"))
        .otherwise(pl.lit("other"))
        .fill_null("other")
    )


def _parse_raw_features(df: pl.DataFrame) -> pl.DataFrame:
    """Convert raw Supabase string columns to typed feature columns.

    Uses native Polars expressions throughout — no Python UDFs.

    Input columns expected (from products table):
        brand, cpu_gen, memory, ssd, hdd, display_size, os, source

    Output columns match ``_FEATURE_COLS``:
        brand (Utf8), cpu_gen (Float32), ram_gb (Int32), ssd_gb (Int32),
        hdd_gb (Int32), display_size (Float32), os_clean (Utf8), source (Utf8)
    """
    return df.with_columns(
        [
            # brand: keep as string, null → "unknown"
            pl.col("brand").fill_null("unknown"),
            # cpu_gen: extract first digit run → Float32, null → -1
            pl.col("cpu_gen")
            .cast(pl.Utf8)
            .str.extract(r"(\d+)", 1)
            .cast(pl.Float32)
            .fill_null(-1.0),
            # memory → ram_gb: "16GB" → 16 (RAM is never in TB)
            pl.col("memory")
            .cast(pl.Utf8)
            .str.extract(r"(\d+)", 1)
            .cast(pl.Int32)
            .fill_null(0)
            .alias("ram_gb"),
            # ssd → ssd_gb: "512GB" → 512, "1TB" → 1024, null → 0
            _storage_expr("ssd").alias("ssd_gb"),
            # hdd → hdd_gb: same rules, null → 0
            _storage_expr("hdd").alias("hdd_gb"),
            # display_size: "14.0インチ" → 14.0, null → -1
            pl.col("display_size")
            .cast(pl.Utf8)
            .str.extract(r"(\d+(?:\.\d+)?)", 1)
            .cast(pl.Float32)
            .fill_null(-1.0),
            # os → os_clean: win7/win8/win10/win11/other
            _os_clean_expr().alias("os_clean"),
            # source: keep as string, null → "unknown"
            pl.col("source").fill_null("unknown"),
        ]
    ).select(_FEATURE_COLS)


# ── sklearn Transformer: feature parsing ──────────────────────────────────────


class _FeatureParser(BaseEstimator, TransformerMixin):
    """Sklearn step: Polars DataFrame with raw string columns → parsed Polars DataFrame.

    Stateless — no learning happens here, just deterministic type transforms.
    """

    def fit(self, X: pl.DataFrame, y: object = None) -> "_FeatureParser":
        """No-op: this transformer is stateless."""
        return self

    def transform(self, X: pl.DataFrame) -> pl.DataFrame:
        """Apply feature parsing rules."""
        return _parse_raw_features(X)


# ── sklearn Transformer: categorical encoding ─────────────────────────────────


class _CatEncoder(BaseEstimator, TransformerMixin):
    """Sklearn step: parsed Polars DataFrame → float32 numpy matrix.

    Fits label encoders on string categorical columns during training.
    Unknown values at prediction time are mapped to an OOV integer bucket.
    Numeric columns are cast to float32 with -1 for nulls.
    """

    feature_cols: list[str] = _FEATURE_COLS
    cat_cols: list[str] = _CAT_COLS

    def fit(self, X: pl.DataFrame, y: object = None) -> "_CatEncoder":
        """Learn label-encoder mappings for each categorical column."""
        self.encoders_: dict[str, dict[str, int]] = {}
        for col in self.cat_cols:
            vals = X[col].cast(pl.Utf8).fill_null("__null__").to_list()
            unique_vals = sorted(set(vals))
            self.encoders_[col] = {v: i for i, v in enumerate(unique_vals)}
        return self

    def transform(self, X: pl.DataFrame) -> np.ndarray:
        """Encode all feature columns to a float32 numpy matrix."""
        check_is_fitted(self, "encoders_")
        arrays: list[np.ndarray] = []
        for col in self.feature_cols:
            if col in self.cat_cols:
                vals = X[col].cast(pl.Utf8).fill_null("__null__").to_list()
                enc = self.encoders_.get(col, {})
                oov = float(len(enc))
                arrays.append(np.array([float(enc.get(v, oov)) for v in vals], dtype=np.float32))
            else:
                arrays.append(X[col].cast(pl.Float32).fill_null(-1.0).to_numpy())
        return np.column_stack(arrays)


# ── Public model class ────────────────────────────────────────────────────────


class LightGBMPriceModel:
    """LightGBM gradient-boosted regressor for used PC price prediction.

    Wraps a three-step sklearn Pipeline internally:
        1. ``_FeatureParser``  — parse raw strings to typed columns (stateless)
        2. ``_CatEncoder``     — label-encode categoricals → float32 matrix
        3. ``LGBMRegressor``   — gradient-boosted regression (MAE objective)

    This design prevents data leakage, makes cross-validation straightforward,
    and serialises the full pipeline in a single joblib file.

    Usage::

        model = LightGBMPriceModel()
        model.fit(X_train, y_train)
        preds = model.predict(X_test)
        model.save(Path("models/price_model.joblib"))

        loaded = LightGBMPriceModel.load(Path("models/price_model.joblib"))

        # Cross-validate via the underlying sklearn pipeline
        from sklearn.model_selection import cross_val_score
        scores = cross_val_score(model.pipeline, X, y_np, cv=5, scoring="neg_mean_absolute_error")
    """

    FEATURE_COLS: list[str] = _FEATURE_COLS
    CAT_COLS: list[str] = _CAT_COLS
    MODEL_VERSION: str = "1.0.0"

    _DEFAULT_LGBM_KWARGS: dict = {
        "objective": "regression_l1",
        "num_leaves": 63,
        "learning_rate": 0.05,
        "n_estimators": 300,
        "colsample_bytree": 0.8,
        "subsample": 0.8,
        "subsample_freq": 5,
        "min_child_samples": 5,
        "verbose": -1,
        "n_jobs": -1,
    }

    def __init__(self, lgbm_kwargs: dict | None = None) -> None:
        merged = {**self._DEFAULT_LGBM_KWARGS, **(lgbm_kwargs or {})}
        self._pipeline: Pipeline = Pipeline(
            [
                ("parser", _FeatureParser()),
                ("encoder", _CatEncoder()),
                ("lgbm", LGBMRegressor(**merged)),
            ]
        )

    @property
    def model_version(self) -> str:
        """Semantic version string for this model."""
        return self.MODEL_VERSION

    @property
    def pipeline(self) -> Pipeline:
        """Expose the underlying sklearn Pipeline (e.g. for cross-validation)."""
        return self._pipeline

    def fit(self, X: pl.DataFrame, y: pl.Series) -> "LightGBMPriceModel":
        """Fit the full pipeline on training data.

        Args:
            X: DataFrame with raw Supabase columns (brand, cpu_gen, memory,
               ssd, hdd, display_size, os, source).
            y: Price series in JPY (integer or float).

        Returns:
            self, for method chaining.
        """
        y_np = y.cast(pl.Float32).to_numpy()
        self._pipeline.fit(X, y_np)
        logger.info("Pipeline fitted on %d rows", len(y))
        return self

    def predict(self, X: pl.DataFrame) -> pl.Series:
        """Predict prices for new listings.

        Args:
            X: DataFrame with the same raw columns as used in fit().

        Returns:
            Integer price predictions in JPY.
        """
        raw = self._pipeline.predict(X)
        return pl.Series("predicted_price", raw.round().astype(np.int64))

    def save(self, path: Path) -> None:
        """Persist the full model (including fitted pipeline) to disk via joblib.

        Args:
            path: Destination file path (e.g. ``Path("models/price_model.joblib")``).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("Model saved to %s", path)

    @classmethod
    def load(cls, path: Path) -> "LightGBMPriceModel":
        """Load a previously saved model.

        Args:
            path: Path to the joblib file produced by :meth:`save`.

        Returns:
            Loaded ``LightGBMPriceModel`` instance.
        """
        model = joblib.load(Path(path))
        if not isinstance(model, cls):
            raise TypeError(f"Expected {cls.__name__}, got {type(model).__name__}")
        logger.info("Model loaded from %s", path)
        return model

    @staticmethod
    def _parse_features(df: pl.DataFrame) -> pl.DataFrame:
        """Parse raw columns to typed feature columns.

        Thin wrapper around the module-level ``_parse_raw_features`` function,
        exposed as a static method for direct testing and scripting.
        """
        return _parse_raw_features(df)
