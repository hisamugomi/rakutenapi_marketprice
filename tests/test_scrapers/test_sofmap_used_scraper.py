"""Tests for src/sofmapscrape_used.py."""

from __future__ import annotations

import asyncio

import polars as pl
import pytest

from src.sofmapscrape_used import (
    SAMPLE_HTML,
    _clean_brand,
    _parse_bracket_specs,
    parse_sofmap_used_listings,
)

REQUIRED_KEYS = {
    "itemCode",
    "itemName",
    "itemUrl",
    "itemPrice",
    "shopName",
    "source",
    "search_query",
    "is_active",
    "scraped_at",
}


@pytest.fixture
def results() -> list[dict]:
    return parse_sofmap_used_listings(SAMPLE_HTML, search_query="sofmap_used_notebooks")


# ── Parser: counts and required keys ─────────────────────────────────────────


def test_returns_correct_count(results):
    assert len(results) == 4


def test_all_rows_have_required_keys(results):
    for row in results:
        assert not (REQUIRED_KEYS - row.keys()), f"Missing: {REQUIRED_KEYS - row.keys()}"


def test_source_is_sofmap_used(results):
    assert all(r["source"] == "sofmap_used" for r in results)


def test_is_active_true(results):
    assert all(r["is_active"] is True for r in results)


def test_search_query_propagated(results):
    assert all(r["search_query"] == "sofmap_used_notebooks" for r in results)


# ── Spot checks: individual items ────────────────────────────────────────────


def test_first_item_lenovo(results):
    r = results[0]
    assert r["itemCode"] == "2133072435673"
    assert "ideapad S540" in r["itemName"]
    assert r["itemPrice"] == 40_980
    assert r["brand"] == "Lenovo"
    assert r["condition"] == "B"
    assert r["shopName"] == "AKIBA パソコン・デジタル館"
    assert r["itemUrl"].startswith("https://used.sofmap.com/r/item/")


def test_second_item_fujitsu(results):
    r = results[1]
    assert r["itemCode"] == "2133071291980"
    assert r["brand"] == "Fujitsu"
    assert r["condition"] == "C"
    assert r["itemPrice"] == 24_980


def test_third_item_dell(results):
    r = results[2]
    assert r["itemCode"] == "2133072078566"
    assert r["brand"] == "Dell"
    assert r["itemPrice"] == 39_980


# ── Spot check: aggregated item ──────────────────────────────────────────────


def test_aggregated_item_vaio(results):
    r = results[3]
    assert r["itemCode"] == "2000453972020"
    assert r["brand"] == "VAIO"
    assert r["itemPrice"] == 42_980
    assert r["condition"] is None  # aggregated items have no rank


# ── Spec extraction from brackets ────────────────────────────────────────────


def test_specs_first_item(results):
    r = results[0]
    assert r["cpu"] == "Core-i5-10210U"
    assert r["memory"] == "8GB"
    assert r["ssd"] == "256GB"
    assert r["hdd"] is None
    assert r["display_size"] == 14.0
    assert "Windows11" in r["os"]


def test_specs_hdd_item(results):
    r = results[1]
    assert r["hdd"] == "1TB"
    assert r["ssd"] is None
    assert r["memory"] == "16GB"
    assert r["display_size"] == 15.6


def test_specs_aggregated(results):
    r = results[3]
    assert r["cpu"] == "Core-i5-1035G1"
    assert r["memory"] == "8GB"
    assert r["ssd"] == "256GB"
    assert r["display_size"] == 13.3


# ── Price and timestamp ──────────────────────────────────────────────────────


def test_price_is_int(results):
    for r in results:
        assert isinstance(r["itemPrice"], int)


def test_scraped_at_jst(results):
    for r in results:
        assert "+09:00" in r["scraped_at"]


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_empty_html():
    assert parse_sofmap_used_listings("") == []


def test_html_without_listings():
    html = '<div class="item-list"><ul class="sys-display-item"></ul></div>'
    assert parse_sofmap_used_listings(html) == []


# ── Brand cleaning ───────────────────────────────────────────────────────────


def test_clean_brand_lenovo():
    assert _clean_brand("Lenovo(レノボジャパン)") == "Lenovo"


def test_clean_brand_fujitsu():
    assert _clean_brand("FUJITSU(富士通)") == "Fujitsu"


def test_clean_brand_hp():
    assert _clean_brand("hp(エイチピー)") == "HP"


def test_clean_brand_other():
    assert _clean_brand("その他メーカー") == ""


# ── Bracket spec parser directly ─────────────────────────────────────────────


def test_parse_bracket_specs_full():
    title = (
        "ThinkPad X1 ［Core-i5-10210U (1.6GHz)／8GB／SSD256GB／14インチワイド／Windows11 Pro MAR］"
    )
    specs = _parse_bracket_specs(title)
    assert specs["cpu"] == "Core-i5-10210U"
    assert specs["memory"] == "8GB"
    assert specs["ssd"] == "256GB"
    assert specs["display_size"] == 14.0
    assert "Windows11" in specs["os"]


def test_parse_bracket_specs_hdd():
    title = "LIFEBOOK ［Core-i7-6700HQ (2.6GHz)／16GB／HDD1TB／15.6インチワイド／Windows10 Home(64ビット)］"
    specs = _parse_bracket_specs(title)
    assert specs["hdd"] == "1TB"
    assert specs["ssd"] is None
    assert specs["memory"] == "16GB"


def test_parse_bracket_specs_no_brackets():
    specs = _parse_bracket_specs("No brackets here")
    assert all(v is None for v in specs.values())


# ── Polars conversion ────────────────────────────────────────────────────────


def test_polars_conversion(results):
    df = pl.from_dicts(results)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 4


def test_item_code_never_null(results):
    df = pl.from_dicts(results)
    assert df["itemCode"].null_count() == 0
    assert all(v != "" for v in df["itemCode"].to_list())


def test_price_history_columns(results):
    df = pl.from_dicts(results)
    assert "itemCode" in df.columns
    assert "itemPrice" in df.columns
    assert "search_query" in df.columns


# ── Playwright / live scrape ─────────────────────────────────────────────────

_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright as _apw

    async def _check() -> bool:
        try:
            async with _apw() as p:
                b = await p.chromium.launch()
                await b.close()
            return True
        except Exception:
            return False

    _PLAYWRIGHT_AVAILABLE = asyncio.run(_check())
except ImportError:
    pass


@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="Playwright not installed")
def test_live_scrape_returns_items():
    from src.sofmapscrape_used import SEARCH_URL, scrape_sofmap_used_page

    html = asyncio.run(scrape_sofmap_used_page(SEARCH_URL))
    rows = parse_sofmap_used_listings(html)
    assert len(rows) > 0
    assert all(r["source"] == "sofmap_used" for r in rows)
    assert all(isinstance(r["itemPrice"], int) for r in rows if r["itemPrice"] is not None)
    assert all(r["itemCode"] for r in rows)
