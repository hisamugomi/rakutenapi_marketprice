"""Training entry point for the LightGBM price model.

Run with::

    uv run python -m src.models.train
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import polars as pl

from src.models.evaluation import report
from src.models.price_model import LightGBMPriceModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MODEL_OUTPUT = Path("models/price_model.joblib")
RANDOM_SEED = 42
TRAIN_RATIO = 0.8


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


def load_training_data(supabase) -> pl.DataFrame:
    """Fetch products + price history from Supabase and join in Polars.

    Returns:
        DataFrame with columns: brand, cpu_gen, memory, ssd, hdd,
        display_size, os, source, price.
    """
    # ── Products ──────────────────────────────────────────────────────────────
    prod_resp = (
        supabase.table("products")
        .select("id,brand,cpu_gen,memory,ssd,hdd,display_size,os,source")
        .not_.is_("brand", "null")
        .execute()
    )
    if not prod_resp.data:
        raise RuntimeError("No products with non-null brand found in database")

    products = pl.from_dicts(prod_resp.data)
    logger.info("Loaded %d products", len(products))

    # ── Price history (paginate in batches of 500) ────────────────────────────
    product_ids = products["id"].to_list()
    price_records: list[dict] = []
    for i in range(0, len(product_ids), 500):
        batch = product_ids[i : i + 500]
        resp = (
            supabase.table("price_history")
            .select("product_id,price")
            .in_("product_id", batch)
            .gt("price", 0)
            .execute()
        )
        price_records.extend(resp.data or [])

    if not price_records:
        raise RuntimeError("No price history records found")

    prices = pl.from_dicts(price_records)
    logger.info("Loaded %d price observations", len(prices))

    # ── Join ──────────────────────────────────────────────────────────────────
    df = products.join(prices, left_on="id", right_on="product_id", how="inner")
    logger.info("Training set: %d rows after join", len(df))
    return df


def train(supabase) -> LightGBMPriceModel:
    """Load data, train model, evaluate, and save.

    Returns:
        Fitted LightGBMPriceModel.
    """
    df = load_training_data(supabase)

    # Raw input cols that _parse_features expects
    raw_cols = ["brand", "cpu_gen", "memory", "ssd", "hdd", "display_size", "os", "source"]
    available = [c for c in raw_cols if c in df.columns]

    # ── 80/20 split ───────────────────────────────────────────────────────────
    n = len(df)
    n_train = int(n * TRAIN_RATIO)
    shuffled = df.sample(fraction=1.0, seed=RANDOM_SEED)
    X_train = shuffled.select(available).head(n_train)
    y_train = shuffled["price"].cast(pl.Int32).head(n_train)
    X_test = shuffled.select(available).tail(n - n_train)
    y_test = shuffled["price"].cast(pl.Int32).tail(n - n_train)

    logger.info("Train: %d rows  Test: %d rows", n_train, n - n_train)

    # ── Fit ───────────────────────────────────────────────────────────────────
    model = LightGBMPriceModel()
    model.fit(X_train, y_train)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    print("\n── Test-set metrics ────────────────────────────────────────────")
    report(model, X_test, y_test)

    # ── Save ──────────────────────────────────────────────────────────────────
    model.save(MODEL_OUTPUT)
    print(f"\nModel saved → {MODEL_OUTPUT}")

    return model


if __name__ == "__main__":
    supabase = _get_supabase_client()
    train(supabase)
