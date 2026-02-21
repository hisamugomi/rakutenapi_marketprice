"""
End-to-end pipeline test against the new products + price_history schema.
Run with: uv run python test_pipeline.py
"""
from __future__ import annotations

from datetime import datetime

import polars as pl
import pytz
import streamlit as st
from supabase import create_client

from src.extract_specs_1 import extract_specs
from src.rakuten_api import fetch_rakuten_items

TEST_QUERY = "L580 -lenovo"
TEST_PAGES = 1


def main() -> None:
    supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["servicerole"])
    print("✓ Supabase client created")

    # ── Fetch ─────────────────────────────────────────────────────────────────
    print(f"\nFetching {TEST_PAGES} page(s) for: '{TEST_QUERY}'")
    raw = fetch_rakuten_items(TEST_QUERY, total_pages=TEST_PAGES)
    assert not raw.is_empty(), "FAIL: No data returned from Rakuten API"
    print(f"✓ {len(raw)} rows after genre filter")

    # ── Transform ─────────────────────────────────────────────────────────────
    jst = pytz.timezone("Asia/Tokyo")
    now_jst = datetime.now(jst).isoformat()

    raw = raw.with_columns([
        (pl.col("itemName") + pl.col("itemCaption")).alias("combined"),
        pl.lit(now_jst).alias("scraped_at"),
        pl.lit(True).alias("is_active"),
        pl.lit(TEST_QUERY).alias("search_query"),
    ])

    extracted = extract_specs(raw, text_col="combined", price_col="itemPrice", name_col="itemName")
    extracted = extracted.with_columns(pl.lit("rakuten").alias("source"))

    print("\nExtraction rates:")
    for col in ["brand", "cpu", "memory", "ssd", "os"]:
        filled = len(extracted) - extracted[col].null_count()
        print(f"  {col:<12} {filled}/{len(extracted)}")

    # ── Upsert products ───────────────────────────────────────────────────────
    _PRODUCT_COLS = [
        "item_code", "source", "item_name", "item_url", "shop_name",
        "search_query", "brand", "model", "cpu", "cpu_gen", "memory",
        "ssd", "hdd", "os", "display_size", "weight", "bluetooth",
        "webcam", "usb_ports", "is_active", "last_seen_at",
    ]
    products_df = (
        extracted
        .rename({"itemCode": "item_code", "itemName": "item_name",
                 "itemUrl": "item_url", "shopName": "shop_name"})
        .with_columns(pl.lit(now_jst).alias("last_seen_at"))
    )
    available = [c for c in _PRODUCT_COLS if c in products_df.columns]
    products_data = products_df.select(available).to_dicts()

    print(f"\nUpserting {len(products_data)} products...")
    supabase.table("products").upsert(products_data, on_conflict="source,item_code").execute()
    print("✓ Products upserted")

    # ── Insert price_history ──────────────────────────────────────────────────
    item_codes = extracted["itemCode"].to_list()
    id_response = supabase.table("products").select("id,item_code").in_("item_code", item_codes).execute()
    id_map = {row["item_code"]: row["id"] for row in id_response.data}

    price_records = [
        {
            "product_id":   id_map[row["itemCode"]],
            "item_code":    row["itemCode"],
            "source":       "rakuten",
            "price":        row["itemPrice"],
            "scraped_at":   now_jst,
            "search_query": TEST_QUERY,
        }
        for row in extracted.select(["itemCode", "itemPrice"]).to_dicts()
        if row["itemCode"] in id_map and row["itemPrice"] is not None
    ]
    print(f"Inserting {len(price_records)} price observations...")
    supabase.table("price_history").insert(price_records).execute()
    print("✓ Price history inserted")

    # ── Verify ────────────────────────────────────────────────────────────────
    print("\nVerifying data in Supabase...")
    result = supabase.table("products").select(
        "item_code, item_name, brand, cpu, memory, ssd, is_active"
    ).in_("item_code", item_codes[:5]).execute()
    assert len(result.data) > 0, "FAIL: Could not read back products"

    rb = pl.DataFrame(result.data, infer_schema_length=None)
    print(f"✓ Verified {len(result.data)} products in Supabase")
    print(rb.select(["item_name", "brand", "cpu", "memory", "ssd", "is_active"]))

    # Price history count
    ph = supabase.table("price_history").select("id", count="exact").in_(
        "item_code", item_codes
    ).execute()
    print(f"\n✓ {ph.count} total price observations for these items in price_history")

    print("\n✓ All tests passed")


if __name__ == "__main__":
    main()
