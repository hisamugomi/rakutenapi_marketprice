from __future__ import annotations

from datetime import datetime

import os

import mojimoji
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


def _get_supabase_client() -> Client:
    """Load credentials from Streamlit secrets (dashboard) or env vars (GitHub Actions)."""
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"]
        servicerole = st.secrets["servicerole"]
    except Exception:
        url = os.environ["SUPABASE_URL"]
        servicerole = os.environ["SERVICEROLE"]
    return create_client(url, servicerole)


def run_scraper() -> None:
    supabase = _get_supabase_client()

    jst = pytz.timezone("Asia/Tokyo")
    now_jst = datetime.now(jst).isoformat()

    # ── Rakuten ──────────────────────────────────────────────────────────────
    for query in QUERIES:
        raw = fetch_rakuten_items(query)
        if raw.is_empty():
            continue

        raw = raw.with_columns([
            (pl.col("itemName") + pl.col("itemCaption"))
            .map_elements(mojimoji.zen_to_han, return_dtype=pl.Utf8)
            .alias("combined"),
            pl.lit(now_jst).alias("scraped_at"),
            pl.lit(True).alias("is_active"),
            pl.lit(query).alias("search_query"),
        ])

        extracted = extract_specs(raw, text_col="combined", price_col="itemPrice", name_col="itemName")
        extracted = extracted.with_columns(pl.lit("rakuten").alias("source"))
        data_list = extracted.to_dicts()

        try:
            supabase.table("rakuten_table").insert(data_list).execute()
            print(f"[rakuten] Inserted {len(data_list)} rows for: {query}")
        except Exception as e:
            print(f"[rakuten] Error saving '{query}': {e}")

    # ── PC Koubou ────────────────────────────────────────────────────────────
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
            data_list = extracted.to_dicts()
            supabase.table("rakuten_table").insert(data_list).execute()
            print(f"[pckoubou] Inserted {len(data_list)} rows with specs")
        except Exception as e:
            print(f"[pckoubou] Error saving to Supabase: {e}")


if __name__ == "__main__":
    run_scraper()
