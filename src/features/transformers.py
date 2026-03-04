"""Sklearn-compatible feature transformers operating on Polars DataFrames.

All transformers are stateless (fit() is a no-op) and use native Polars
expressions for maximum performance — no Python-level map_elements UDFs.
"""

from __future__ import annotations

import polars as pl
from sklearn.base import BaseEstimator, TransformerMixin

from src.features.cpu_benchmark import get_benchmark_score


class RamGbExtractor(BaseEstimator, TransformerMixin):
    """Extract RAM in GB from a string column (e.g. "16GB" → 16).

    Input column: ``memory``. Output column: ``ram_gb`` (Int32, 0 for nulls).
    """

    def fit(self, X: pl.DataFrame, y: object = None) -> "RamGbExtractor":
        """No-op — stateless transformer."""
        return self

    def transform(self, X: pl.DataFrame) -> pl.DataFrame:
        """Add ``ram_gb`` column parsed from ``memory``."""
        if "memory" not in X.columns:
            return X.with_columns(pl.lit(0).cast(pl.Int32).alias("ram_gb"))
        return X.with_columns(
            pl.col("memory")
            .cast(pl.Utf8)
            .str.extract(r"(\d+)", 1)
            .cast(pl.Int32)
            .fill_null(0)
            .alias("ram_gb")
        )


class StorageExtractor(BaseEstimator, TransformerMixin):
    """Extract storage in GB from a string column.

    Handles "512GB" → 512 and "1TB" → 1024 conversions.

    Args:
        col_in: Source column name (e.g. ``"ssd"``).
        col_out: Destination column name (e.g. ``"ssd_gb"``).
    """

    def __init__(self, col_in: str = "ssd", col_out: str = "ssd_gb") -> None:
        self.col_in = col_in
        self.col_out = col_out

    def fit(self, X: pl.DataFrame, y: object = None) -> "StorageExtractor":
        """No-op — stateless transformer."""
        return self

    def transform(self, X: pl.DataFrame) -> pl.DataFrame:
        """Add output column with storage capacity in GB."""
        if self.col_in not in X.columns:
            return X.with_columns(pl.lit(0).cast(pl.Int32).alias(self.col_out))
        s = pl.col(self.col_in).cast(pl.Utf8)
        expr = (
            pl.when(s.str.to_uppercase().str.contains("TB", literal=True))
            .then(s.str.extract(r"(\d+)", 1).cast(pl.Int32) * 1024)
            .otherwise(s.str.extract(r"(\d+)", 1).cast(pl.Int32))
            .fill_null(0)
            .alias(self.col_out)
        )
        return X.with_columns(expr)


class OsNormalizer(BaseEstimator, TransformerMixin):
    """Normalise OS strings to canonical buckets.

    Buckets: ``win7``, ``win8``, ``win10``, ``win11``, ``other``.

    Input column: ``os``. Output column: ``os_clean``.
    """

    def fit(self, X: pl.DataFrame, y: object = None) -> "OsNormalizer":
        """No-op — stateless transformer."""
        return self

    def transform(self, X: pl.DataFrame) -> pl.DataFrame:
        """Add ``os_clean`` column."""
        if "os" not in X.columns:
            return X.with_columns(pl.lit("other").alias("os_clean"))
        s = pl.col("os").cast(pl.Utf8)
        expr = (
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
            .alias("os_clean")
        )
        return X.with_columns(expr)


class CpuBenchmarkAdder(BaseEstimator, TransformerMixin):
    """Add a ``cpu_benchmark`` column using PassMark scores via fuzzy lookup.

    Input column: ``cpu``. Output column: ``cpu_benchmark`` (Float64, null if
    no match found above the confidence threshold).
    """

    def fit(self, X: pl.DataFrame, y: object = None) -> "CpuBenchmarkAdder":
        """No-op — stateless transformer."""
        return self

    def transform(self, X: pl.DataFrame) -> pl.DataFrame:
        """Add ``cpu_benchmark`` column."""
        if "cpu" not in X.columns:
            return X.with_columns(pl.lit(None).cast(pl.Float64).alias("cpu_benchmark"))
        scores = [get_benchmark_score(v) for v in X["cpu"].cast(pl.Utf8).to_list()]
        return X.with_columns(pl.Series("cpu_benchmark", scores, dtype=pl.Float64))
