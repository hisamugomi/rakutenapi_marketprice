"""Tests for src/pcwrapscrape.py — parser unit tests + integration readiness."""
from __future__ import annotations

import asyncio

import polars as pl
import pytest

from src.pcwrapscrape import SAMPLE_HTML, parse_pcwrap_listings

# ── Playwright availability check ─────────────────────────────────────────────
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright as _apw

    async def _check_browser() -> bool:
        try:
            async with _apw() as p:
                browser = await p.chromium.launch()
                await browser.close()
            return True
        except Exception:
            return False

    _PLAYWRIGHT_AVAILABLE = asyncio.run(_check_browser())
except ImportError:
    pass

# ── Column maps mirroring scraper.py integration logic ───────────────────────
_RENAME_MAP = {
    "itemCode": "item_code",
    "itemName": "item_name",
    "itemUrl": "item_url",
    "shopName": "shop_name",
}
_PRODUCT_COLS = [
    "item_code", "source", "item_name", "item_url", "shop_name",
    "search_query", "brand", "model", "cpu", "memory", "ssd", "hdd",
    "os", "display_size", "is_active",
]

REQUIRED_KEYS = {
    "itemCode", "itemName", "itemUrl", "itemPrice",
    "shopName", "source", "search_query", "is_active", "scraped_at",
    "brand", "model", "os", "cpu", "memory", "ssd", "hdd", "display_size",
    "condition",
}


@pytest.fixture
def results() -> list[dict]:
    return parse_pcwrap_listings(SAMPLE_HTML)


# ── Schema ────────────────────────────────────────────────────────────────────

def test_returns_correct_count(results):
    """SAMPLE_HTML has 3 items — should parse exactly 3."""
    assert len(results) == 3


def test_all_rows_have_required_keys(results):
    for row in results:
        missing = REQUIRED_KEYS - row.keys()
        assert not missing, f"Row missing keys: {missing}"


def test_source_is_pcwrap(results):
    assert all(r["source"] == "pcwrap" for r in results)


def test_shop_name_is_pcwrap(results):
    assert all(r["shopName"] == "PCwrap" for r in results)


def test_is_active_is_true(results):
    """None of the sample items have the sold-out image."""
    assert all(r["is_active"] is True for r in results)


def test_search_query_default(results):
    assert all(r["search_query"] == "pcwrap_notebooks" for r in results)


def test_scraped_at_is_set(results):
    for row in results:
        assert row["scraped_at"]
        assert "+09:00" in row["scraped_at"]


# ── First row spot-check (Panasonic Let's note) ───────────────────────────────

def test_first_item_name(results):
    assert results[0]["itemName"] == "Panasonic Let's note CF-SV7RDYVS"


def test_first_item_code(results):
    assert results[0]["itemCode"] == "100123"


def test_first_item_price(results):
    assert results[0]["itemPrice"] == 29800


def test_first_item_price_is_int(results):
    assert isinstance(results[0]["itemPrice"], int)


def test_first_item_brand(results):
    assert results[0]["brand"] == "Panasonic"


def test_first_item_model(results):
    assert results[0]["model"] == "Let's note CF-SV7RDYVS"


def test_first_item_os(results):
    assert results[0]["os"] == "Windows 11 Pro"


def test_first_item_cpu(results):
    assert "Core i5" in results[0]["cpu"]


def test_first_item_memory(results):
    assert results[0]["memory"] == "8GB"


def test_first_item_ssd(results):
    assert results[0]["ssd"] == "256GB"
    assert results[0]["hdd"] is None


def test_first_item_display_size(results):
    assert results[0]["display_size"] == 12.1


def test_first_item_condition(results):
    assert results[0]["condition"] == "A"


def test_first_item_url(results):
    assert results[0]["itemUrl"] == "https://www.pcwrap.com/item/detail/100123"


# ── Second row spot-check (Lenovo ThinkPad) ───────────────────────────────────

def test_second_item_price(results):
    assert results[1]["itemPrice"] == 38500


def test_second_item_memory(results):
    assert results[1]["memory"] == "16GB"


def test_second_item_ssd(results):
    assert results[1]["ssd"] == "512GB"


# ── Third row: HDD storage ────────────────────────────────────────────────────

def test_hdd_row(results):
    """Third item has HDD — should go to hdd column, ssd should be None."""
    assert results[2]["hdd"] == "500GB"
    assert results[2]["ssd"] is None


def test_third_item_price(results):
    assert results[2]["itemPrice"] == 14800


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_html_returns_empty_list():
    assert parse_pcwrap_listings("") == []


def test_html_without_list_returns_empty_list():
    assert parse_pcwrap_listings("<html><body><p>nothing</p></body></html>") == []


# ── Polars conversion ─────────────────────────────────────────────────────────

def test_polars_conversion_succeeds(results):
    df = pl.from_dicts(results)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 3


def test_polars_schema_has_pipeline_columns(results):
    df = pl.from_dicts(results)
    for col in [
        "itemCode", "itemName", "itemUrl", "itemPrice",
        "shopName", "source", "search_query", "is_active", "scraped_at",
        "brand", "model", "cpu", "os", "memory", "ssd", "hdd", "display_size",
    ]:
        assert col in df.columns


# ── _upsert_batch column mapping ──────────────────────────────────────────────

def test_after_rename_product_cols_present(results):
    df = pl.from_dicts(results).rename(_RENAME_MAP)
    assert set(_PRODUCT_COLS).issubset(set(df.columns))


def test_item_code_never_null(results):
    """itemCode is the upsert conflict key — must be non-empty for every row."""
    df = pl.from_dicts(results)
    assert df["itemCode"].null_count() == 0
    assert all(v != "" for v in df["itemCode"].to_list())


def test_display_size_is_float_or_none(results):
    for row in results:
        assert row["display_size"] is None or isinstance(row["display_size"], float)
    # All sample items have a screen size
    assert all(r["display_size"] is not None for r in results)


# ── price_history readiness ───────────────────────────────────────────────────

def test_item_price_is_int_or_none(results):
    for row in results:
        assert row["itemPrice"] is None or isinstance(row["itemPrice"], int)


def test_price_history_fields_present(results):
    df = pl.from_dicts(results)
    for col in ["itemCode", "itemPrice", "search_query"]:
        assert col in df.columns


def test_no_null_item_codes_in_price_rows(results):
    for row in results:
        if row["itemPrice"] is not None:
            assert row["itemCode"]


# ── Playwright / live scrape ──────────────────────────────────────────────────

def test_pcwrap_playwright_browser_installed():
    assert _PLAYWRIGHT_AVAILABLE, (
        "Playwright Chromium not found. "
        "Run: uv run playwright install chromium --with-deps"
    )


@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="Playwright browser not installed")
def test_pcwrap_live_scrape_returns_items():
    from src.pcwrapscrape import LISTINGS_URL, scrape_pcwrap

    rows = asyncio.run(scrape_pcwrap(LISTINGS_URL))
    assert len(rows) > 0
    assert all(r["source"] == "pcwrap" for r in rows)
    assert all(r["shopName"] == "PCwrap" for r in rows)
    assert all(isinstance(r["itemPrice"], int) for r in rows if r["itemPrice"] is not None)
    assert all(r["itemCode"] for r in rows)
    assert all(r["itemUrl"].startswith("https://www.pcwrap.com/") for r in rows)
