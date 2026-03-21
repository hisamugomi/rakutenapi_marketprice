"""Backfill the model column in products using the regex-based model extractor.

Fetches every product, runs extract_model() on item_name, and upserts the
result back to Supabase in batches.  Only rows where extract_model() returns
a non-None value are updated — existing good data is never overwritten with
None.

Run with::

    uv run python -m src.pipeline.backfill_models
"""
from __future__ import annotations

import logging
import os

from src.features.model_extractor import extract_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_BATCH_SIZE = 500
_PAGE_SIZE = 1000


def _get_supabase_client():
    from supabase import create_client

    try:
        import streamlit as st

        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["servicerole"]
    except Exception:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SERVICEROLE"]
    return create_client(url, key)


def _fetch_all_products(client) -> list[dict]:
    """Paginate through products to bypass the 1000-row cap."""
    rows: list[dict] = []
    offset = 0
    while True:
        resp = (
            client.table("products")
            .select("id, item_code, source, item_name")
            .range(offset, offset + _PAGE_SIZE - 1)
            .execute()
        )
        rows.extend(resp.data)
        if len(resp.data) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


def _update_batch(client, batch: list[dict]) -> None:
    # Use individual UPDATE calls (PATCH /products?id=eq.<uuid>).
    # Slower than upsert but avoids NOT NULL constraint violations on partial rows.
    for row in batch:
        client.table("products").update({"model": row["model"]}).eq("id", row["id"]).execute()


def backfill(client=None) -> int:
    """Run the backfill.

    Args:
        client: Authenticated Supabase client (created automatically if None).

    Returns:
        Number of products whose model column was updated.
    """
    if client is None:
        client = _get_supabase_client()

    logger.info("Fetching all products...")
    products = _fetch_all_products(client)
    logger.info("Fetched %d products", len(products))

    updates: list[dict] = []
    matched = 0

    for row in products:
        model = extract_model(row.get("item_name") or "")
        if model is not None:
            updates.append({"id": row["id"], "model": model})
            matched += 1

    logger.info(
        "extract_model matched %d / %d products (%.0f%%)",
        matched,
        len(products),
        100 * matched / len(products) if products else 0,
    )

    if not updates:
        logger.info("Nothing to update.")
        return 0

    # Upsert in batches to avoid request size limits
    total_batches = -(-len(updates) // _BATCH_SIZE)
    for i in range(0, len(updates), _BATCH_SIZE):
        batch = updates[i : i + _BATCH_SIZE]
        _update_batch(client, batch)
        logger.info("Updated batch %d/%d (%d rows)", i // _BATCH_SIZE + 1, total_batches, len(batch))

    logger.info("Done. %d products updated.", matched)
    return matched


if __name__ == "__main__":
    updated = backfill()
    print(f"Backfill complete — {updated} products updated.")
