from __future__ import annotations

import os
import time

import polars as pl
import requests

API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"

_COLUMNS = ["itemName", "itemPrice", "itemUrl", "itemCaption", "genreId", "shopName", "itemCode"]

_EMPTY_SCHEMA = {
    "itemName": pl.Utf8,
    "itemPrice": pl.Int64,
    "itemUrl": pl.Utf8,
    "itemCaption": pl.Utf8,
    "genreId": pl.Utf8,
    "shopName": pl.Utf8,
    "itemCode": pl.Utf8,
}


def fetch_rakuten_items(keyword: str, total_pages: int = 30) -> pl.DataFrame:
    """Fetch used computer listings from Rakuten Ichiba API.

    Returns a Polars DataFrame with columns defined in _COLUMNS.
    Returns an empty DataFrame (correct schema) if nothing is found.
    """
    timeout = 10
    all_items: list[dict] = []

    app_id = os.environ.get("RAKUTEN_APP_ID")
    affiliate_id = os.environ.get("RAKUTEN_AFFILIATE_ID")

    # Fall back to Streamlit secrets (local dev / Streamlit Cloud)
    if not app_id:
        try:
            import streamlit as st
            app_id = st.secrets.get("RAKUTEN_APP_ID")
            affiliate_id = st.secrets.get("RAKUTEN_AFFILIATE_ID")
        except Exception:
            pass

    for page in range(1, total_pages + 1):
        params: dict = {
            "applicationId": app_id,
            "format": "json",
            "keyword": keyword,
            "page": page,
            "usedFlag": 1,
            "genreId": 100026,
            "hits": 30,
            "sort": "-itemPrice",
        }
        if affiliate_id:
            params["affiliateId"] = affiliate_id

        try:
            response = requests.get(API_URL, params=params, timeout=timeout)
            response.raise_for_status()
            raw_json = response.json()

            if "error" in raw_json:
                print(f"[rakuten] API error: {raw_json.get('error_description', 'unknown')}")
                break

            items = raw_json.get("Items", [])
            if not items:
                print(f"[rakuten] No more items at page {page}. Stopping.")
                break

            for wrapper in items:
                item = wrapper["Item"]
                all_items.append({col: item.get(col) for col in _COLUMNS})

            print(f"[rakuten] Page {page}: {len(items)} items scraped.")
            time.sleep(3)

        except requests.exceptions.Timeout:
            print(f"[rakuten] Timeout on page {page}, skipping.")
        except requests.exceptions.HTTPError as e:
            print(f"[rakuten] HTTP {e.response.status_code} on page {page}, stopping.")
            break
        except Exception as e:
            print(f"[rakuten] Unexpected error on page {page}: {e}")

    if not all_items:
        return pl.DataFrame(schema=_EMPTY_SCHEMA)

    df = pl.from_dicts(all_items, schema_overrides={"itemPrice": pl.Int64})

    # Keep computers only (genreId 100040) — filter out accessories, cables, etc.
    before = len(df)
    df = df.filter(pl.col("genreId").cast(pl.Utf8) == "100040")
    print(f"[rakuten] Filtered {before - len(df)} non-computer items, {len(df)} remaining.")

    return df
