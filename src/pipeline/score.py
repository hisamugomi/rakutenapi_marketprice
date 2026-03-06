"""Batch scoring entry point — predict prices for all active products.

Run with::

    uv run python -m src.pipeline.score
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import polars as pl

from src.models.price_model import LightGBMPriceModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_PATH = Path("models/price_model.joblib")


def _get_supabase_client():
    """Load credentials from Streamlit secrets or environment variables."""
    from supabase import create_client

    try:
        import streamlit as st

        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["servicerole"]
    except Exception:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SERVICEROLE"]
    return create_client(url, key)


def load_active_products(supabase) -> pl.DataFrame:
    """Fetch all active products from Supabase.

    Returns:
        DataFrame with columns: id, brand, cpu_gen, memory, ssd,
        hdd, display_size, os, source.
    """
    resp = (
        supabase.table("products")
        .select("id,brand,cpu_gen,memory,ssd,hdd,display_size,os,source")
        .eq("is_active", True)
        .execute()
    )
    if not resp.data:
        logger.warning("No active products found")
        return pl.DataFrame()
    df = pl.from_dicts(resp.data)
    logger.info("Loaded %d active products", len(df))
    return df


def save_predictions(
    supabase,
    product_ids: list[str],
    predicted_prices: pl.Series,
    model_version: str,
) -> None:
    """Insert price prediction records into Supabase.

    Args:
        supabase: Authenticated Supabase client.
        product_ids: UUIDs of the scored products.
        predicted_prices: Predicted prices in JPY.
        model_version: Version string from the loaded model.
    """
    records = [
        {
            "product_id": pid,
            "predicted_price": int(price),
            "model_version": model_version,
        }
        for pid, price in zip(product_ids, predicted_prices.to_list())
    ]
    supabase.table("price_predictions").insert(records).execute()
    logger.info("Inserted %d predictions (model_version=%s)", len(records), model_version)


def score(supabase, model: LightGBMPriceModel | None = None) -> pl.DataFrame:
    """Load model, predict, and persist to price_predictions table.

    Args:
        supabase: Authenticated Supabase client.
        model: Pre-loaded model (loads from MODEL_PATH if None).

    Returns:
        DataFrame of scored products with predicted_price column.
    """
    if model is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model file not found at {MODEL_PATH}. Run `uv run python -m src.models.train` first."
            )
        model = LightGBMPriceModel.load(MODEL_PATH)

    products = load_active_products(supabase)
    if products.is_empty():
        return pl.DataFrame()

    raw_cols = ["brand", "cpu_gen", "memory", "ssd", "hdd", "display_size", "os", "source"]
    available = [c for c in raw_cols if c in products.columns]
    X = products.select(available)

    predictions = model.predict(X)
    product_ids = products["id"].to_list()

    save_predictions(supabase, product_ids, predictions, model.model_version)

    return products.with_columns(predictions)


if __name__ == "__main__":
    supabase = _get_supabase_client()
    result = score(supabase)
    if not result.is_empty():
        print(f"Scored {len(result)} products.")
