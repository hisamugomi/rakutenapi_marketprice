"""Feature engineering entry point for used-PC price models.

Applies all transformers in sequence to produce a clean feature matrix
from raw Supabase product data.
"""

from __future__ import annotations

import logging

import polars as pl

from src.features.transformers import (
    CpuBenchmarkAdder,
    OsNormalizer,
    RamGbExtractor,
    StorageExtractor,
)

logger = logging.getLogger(__name__)


class FeatureBuilder:
    """Builds the full feature matrix from raw products data.

    Applies all transformers in sequence and returns a clean Polars DataFrame
    ready for ML model input. Missing source columns are filled with safe
    defaults rather than raising errors.

    Usage::

        builder = FeatureBuilder()
        features = builder.build(raw_products_df)
        model.fit(features, prices)
    """

    FEATURE_COLS: list[str] = [
        "brand",
        "cpu_gen",
        "ram_gb",
        "ssd_gb",
        "hdd_gb",
        "display_size",
        "os_clean",
        "source",
        "cpu_benchmark",
    ]

    def __init__(self) -> None:
        """Initialise FeatureBuilder with the default transformer chain."""
        self._ram_extractor = RamGbExtractor()
        self._ssd_extractor = StorageExtractor(col_in="ssd", col_out="ssd_gb")
        self._hdd_extractor = StorageExtractor(col_in="hdd", col_out="hdd_gb")
        self._os_normalizer = OsNormalizer()
        self._cpu_benchmark = CpuBenchmarkAdder()

    def build(self, df: pl.DataFrame) -> pl.DataFrame:
        """Transform raw products DataFrame to feature matrix.

        Args:
            df: Raw products DataFrame from Supabase (any subset of columns).
                Expected source columns: brand, cpu_gen, memory, ssd, hdd,
                display_size, os, source, cpu.

        Returns:
            DataFrame with ``FEATURE_COLS`` columns. Missing source columns
            are filled with nulls/defaults (0 for numeric, "unknown" for strings).
        """
        out = df

        # ── Apply transformers ────────────────────────────────────────────────
        out = self._ram_extractor.transform(out)
        out = self._ssd_extractor.transform(out)
        out = self._hdd_extractor.transform(out)
        out = self._os_normalizer.transform(out)
        out = self._cpu_benchmark.transform(out)

        # ── Normalise cpu_gen → Float32 ───────────────────────────────────────
        if "cpu_gen" in out.columns:
            out = out.with_columns(
                pl.col("cpu_gen")
                .cast(pl.Utf8)
                .str.extract(r"(\d+)", 1)
                .cast(pl.Float32)
                .fill_null(-1.0)
                .alias("cpu_gen")
            )
        else:
            out = out.with_columns(pl.lit(-1.0).cast(pl.Float32).alias("cpu_gen"))

        # ── Ensure brand / source string columns ─────────────────────────────
        for col, default in [("brand", "unknown"), ("source", "unknown")]:
            if col in out.columns:
                out = out.with_columns(pl.col(col).cast(pl.Utf8).fill_null(default))
            else:
                out = out.with_columns(pl.lit(default).alias(col))

        # ── Ensure display_size as Float32 ───────────────────────────────────
        if "display_size" in out.columns:
            out = out.with_columns(
                pl.col("display_size")
                .cast(pl.Utf8)
                .str.extract(r"(\d+(?:\.\d+)?)", 1)
                .cast(pl.Float32)
                .fill_null(-1.0)
                .alias("display_size")
            )
        else:
            out = out.with_columns(pl.lit(-1.0).cast(pl.Float32).alias("display_size"))

        # ── Select only FEATURE_COLS in declared order ────────────────────────
        available = [c for c in self.FEATURE_COLS if c in out.columns]
        missing = [c for c in self.FEATURE_COLS if c not in out.columns]
        if missing:
            logger.warning("FeatureBuilder: missing output columns %s", missing)

        result = out.select(available)
        logger.debug("FeatureBuilder produced %d rows × %d cols", len(result), len(available))
        return result
