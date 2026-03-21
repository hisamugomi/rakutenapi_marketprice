"""Tests for src/qualitscrape.py."""
from __future__ import annotations

import polars as pl
import pytest

from src.qualitscrape import SAMPLE_HTML, parse_qualit_listings

REQUIRED_KEYS = {
    "itemCode", "itemName", "itemUrl", "itemPrice",
    "shopName", "source", "search_query", "is_active", "scraped_at",
}


@pytest.fixture
def results() -> list[dict]:
    return parse_qualit_listings(SAMPLE_HTML)


# ── Parser ────────────────────────────────────────────────────────────────────

def test_returns_correct_count(results):
    assert len(results) == 3


def test_all_rows_have_required_keys(results):
    for row in results:
        assert not (REQUIRED_KEYS - row.keys()), f"Missing keys: {REQUIRED_KEYS - row.keys()}"


def test_source_is_qualit(results):
    assert all(r["source"] == "qualit" for r in results)


def test_is_active_is_true(results):
    assert all(r["is_active"] is True for r in results)


def test_search_query_propagated(results):
    assert all(r["search_query"] == "qualit_notebooks" for r in results)


def test_first_row_spot_check(results):
    row = results[0]
    assert "ThinkPad E16" in row["itemName"]
    assert row["itemPrice"] == 95700
    assert row["itemUrl"].startswith("https://www.yrl-qualit.com/")
    assert row["shopName"] == "Qualit"
    assert row["brand"] == "Lenovo"
    assert row["cpu"] is not None and "i5" in row["cpu"]
    assert row["memory"] == "16GB"
    assert row["ssd"] == "256GB"
    assert row["condition"] == "C"


def test_second_row_spot_check(results):
    row = results[1]
    assert "ProBook 450" in row["itemName"]
    assert row["itemPrice"] == 57200
    assert row["brand"] == "HP"
    assert row["memory"] == "32GB"
    assert row["condition"] == "C"


def test_junk_condition_parsed(results):
    """The third item has [訳あり品] which should map to 'Junk'."""
    row = results[2]
    assert row["condition"] == "Junk"
    assert row["itemPrice"] == 31900


def test_item_price_is_int(results):
    for row in results:
        assert isinstance(row["itemPrice"], int), f"itemPrice should be int, got {type(row['itemPrice'])}"


def test_scraped_at_has_jst_offset(results):
    for row in results:
        assert "+09:00" in row["scraped_at"]


def test_empty_html_returns_empty():
    assert parse_qualit_listings("") == []


def test_html_without_listings_returns_empty():
    assert parse_qualit_listings("<html><body><p>Nothing here</p></body></html>") == []


# ── Comment spec parsing ─────────────────────────────────────────────────────

def test_comment_specs_extracted(results):
    """Verify structured specs are parsed from HTML comments."""
    row = results[0]
    assert row["itemCode"] == "5726342c"
    assert row["os"] is not None and "Windows11" in row["os"]
    assert row["cpu_gen"] == "第13世代"


def test_model_from_comments(results):
    row = results[0]
    assert row["model"] is not None
    assert "ThinkPad E16 Gen 1" in row["model"]


# ── Polars + mapping ─────────────────────────────────────────────────────────

def test_polars_conversion_succeeds(results):
    df = pl.from_dicts(results)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 3


def test_item_code_never_null(results):
    df = pl.from_dicts(results)
    assert df["itemCode"].null_count() == 0
    assert all(v != "" for v in df["itemCode"].to_list())


def test_required_columns_for_price_history(results):
    """itemCode, itemPrice, search_query must all be present."""
    df = pl.from_dicts(results)
    assert "itemCode" in df.columns
    assert "itemPrice" in df.columns
    assert "search_query" in df.columns


def test_every_priced_row_has_item_code(results):
    df = pl.from_dicts(results)
    priced = df.filter(pl.col("itemPrice").is_not_null())
    assert priced["itemCode"].null_count() == 0


# ── Live scrape (optional) ───────────────────────────────────────────────────

@pytest.mark.skipif(True, reason="Live scrape — run manually with pytest -k test_live")
def test_live_scrape_returns_items():
    from src.qualitscrape import run_qualit_scraper
    rows = run_qualit_scraper(max_pages=1)
    assert len(rows) > 0
    assert all(r["source"] == "qualit" for r in rows)
    assert all(isinstance(r["itemPrice"], int) for r in rows if r["itemPrice"] is not None)
    assert all(r["itemCode"] for r in rows)
