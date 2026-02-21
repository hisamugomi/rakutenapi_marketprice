from __future__ import annotations

import os
from datetime import datetime

import polars as pl
import pytz
from supabase import Client, create_client

from src.extract_specs_1 import extract_specs
from src.pckoboscrape import run_pckoubou_scraper
from src.rakuten_api import fetch_rakuten_items

QUERIES = [
    "L580 -lenovo",
    "L590 -lenovo",
    "L390 -lenovo",
    "Latitude 5300 -dell",
    "Latitude 5400 -dell",
    "Latitude 5490 -dell",
    "Latitude 5500 -dell",
    "Latitude 5590 -dell",
]

# Columns that map to the products table
_PRODUCT_COLS = [
    "item_code", "source", "item_name", "item_url", "shop_name",
    "search_query", "brand", "model", "cpu", "cpu_gen", "memory",
    "ssd", "hdd", "os", "display_size", "weight", "bluetooth",
    "webcam", "usb_ports", "is_active", "last_seen_at",
]


def _get_supabase_client() -> Client:
    """Load credentials from Streamlit secrets (local/cloud) or env vars (GitHub Actions)."""
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"]
        servicerole = st.secrets["servicerole"]
    except Exception:
        url = os.environ["SUPABASE_URL"]
        servicerole = os.environ["SERVICEROLE"]
    return create_client(url, servicerole)


def _upsert_batch(
    supabase: Client,
    extracted: pl.DataFrame,
    source: str,
    now_jst: str,
) -> None:
    """
    1. Upsert into products (specs + last_seen_at).
    2. Insert a price observation into price_history for every row.
    3. Mark products from this source that were NOT seen this run as inactive.
    """
    # ── Rename columns to match products schema ──────────────────────────────
    products_df = (
        extracted
        .rename({
            "itemCode": "item_code",
            "itemName": "item_name",
            "itemUrl":  "item_url",
            "shopName": "shop_name",
        })
        .with_columns(pl.lit(now_jst).alias("last_seen_at"))
    )

    available_cols = [c for c in _PRODUCT_COLS if c in products_df.columns]
    products_data = products_df.select(available_cols).to_dicts()

    # ── 1. Upsert products ───────────────────────────────────────────────────
    supabase.table("products").upsert(
        products_data, on_conflict="source,item_code"
    ).execute()
    print(f"  Upserted {len(products_data)} products")

    # ── 2. Get product IDs to link price_history ─────────────────────────────
    item_codes = extracted["itemCode"].to_list()
    id_response = (
        supabase.table("products")
        .select("id,item_code")
        .in_("item_code", item_codes)
        .execute()
    )
    id_map = {row["item_code"]: row["id"] for row in id_response.data}

    # ── 3. Insert price observations ─────────────────────────────────────────
    price_records = [
        {
            "product_id":   id_map[row["itemCode"]],
            "item_code":    row["itemCode"],
            "source":       source,
            "price":        row["itemPrice"],
            "scraped_at":   now_jst,
            "search_query": row.get("search_query"),
        }
        for row in extracted.select(["itemCode", "itemPrice", "search_query"]).to_dicts()
        if row["itemCode"] in id_map and row["itemPrice"] is not None
    ]
    if price_records:
        supabase.table("price_history").insert(price_records).execute()
        print(f"  Inserted {len(price_records)} price observations")

    # ── 4. Mark unseen items inactive ────────────────────────────────────────
    supabase.table("products").update({"is_active": False}).eq(
        "source", source
    ).not_.in_("item_code", item_codes).execute()
    print(f"  Marked unseen {source} items inactive")


def run_scraper() -> None:
    supabase = _get_supabase_client()
    jst = pytz.timezone("Asia/Tokyo")
    now_jst = datetime.now(jst).isoformat()

    # ── Rakuten ──────────────────────────────────────────────────────────────
    for query in QUERIES:
        print(f"\n[rakuten] {query}")
        raw = fetch_rakuten_items(query)
        if raw.is_empty():
            print("  No results.")
            continue

        raw = raw.with_columns([
            (pl.col("itemName") + pl.col("itemCaption")).alias("combined"),
            pl.lit(now_jst).alias("scraped_at"),
            pl.lit(True).alias("is_active"),
            pl.lit(query).alias("search_query"),
        ])

        extracted = extract_specs(raw, text_col="combined", price_col="itemPrice", name_col="itemName")
        extracted = extracted.with_columns(pl.lit("rakuten").alias("source"))

        try:
            _upsert_batch(supabase, extracted, "rakuten", now_jst)
        except Exception as e:
            print(f"  Error: {e}")

    # ── PC Koubou ────────────────────────────────────────────────────────────
    print("\n[pckoubou] Scraping...")
    pckoubou_data = run_pckoubou_scraper()
    if pckoubou_data:
        try:
            pckoubou_pl = pl.from_dicts(pckoubou_data)
            pckoubou_pl = pckoubou_pl.with_columns([
                pl.col("itemName").alias("combined"),
                pl.lit(None).cast(pl.Utf8).alias("genreId"),
                pl.lit(None).cast(pl.Utf8).alias("shopName"),
            ])
            extracted = extract_specs(
                pckoubou_pl, text_col="combined", price_col="itemPrice", name_col="itemName"
            )
            extracted = extracted.with_columns(pl.lit("pckoubou").alias("source"))
            _upsert_batch(supabase, extracted, "pckoubou", now_jst)
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    run_scraper()
