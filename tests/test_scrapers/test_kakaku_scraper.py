"""Tests for src/kakakucom_scrape.py — parser unit tests using static HTML."""
from __future__ import annotations

import asyncio

import polars as pl
import pytest

from src.kakakucom_scrape import SAMPLE_HTML, parse_kakaku_listings

# ── Playwright availability check (runs once at import time) ──────────────────
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
    "ram": "memory",
    "storage": "ssd",
}
_PRODUCT_COLS = [
    "item_code", "source", "item_name", "item_url", "shop_name",
    "search_query", "model", "cpu", "memory", "ssd", "os",
    "display_size", "is_active",
]

REQUIRED_KEYS = {
    "itemCode", "itemName", "itemUrl", "itemPrice",
    "rank", "os", "cpu", "storage", "ram", "screen",
    "shopName", "listedDate", "scraped_at", "search_query", "source", "is_active",
}


@pytest.fixture
def results() -> list[dict]:
    return parse_kakaku_listings(SAMPLE_HTML, search_query="L390")


# ── Schema ────────────────────────────────────────────────────────────────────

def test_returns_correct_count(results):
    """Sample HTML has 3 products — should parse exactly 3."""
    assert len(results) == 3


def test_all_rows_have_required_keys(results):
    for row in results:
        missing = REQUIRED_KEYS - row.keys()
        assert not missing, f"Row missing keys: {missing}"


def test_source_is_kakaku(results):
    assert all(r["source"] == "kakaku" for r in results)


def test_is_active_is_true(results):
    assert all(r["is_active"] is True for r in results)


def test_search_query_propagated(results):
    assert all(r["search_query"] == "L390" for r in results)


# ── First row spot-check ──────────────────────────────────────────────────────

def test_first_item_name(results):
    assert results[0]["itemName"] == "ThinkPad L390 20NSS0W100"


def test_first_item_price(results):
    assert results[0]["itemPrice"] == 19400


def test_first_item_price_is_int(results):
    assert isinstance(results[0]["itemPrice"], int)


def test_first_item_rank(results):
    assert results[0]["rank"] == "Bランク"


def test_first_item_os(results):
    assert results[0]["os"] == "Windows 11 Pro"


def test_first_item_cpu(results):
    assert results[0]["cpu"] == "Core i3"


def test_first_item_storage(results):
    assert results[0]["storage"] == "128GB"


def test_first_item_ram(results):
    assert results[0]["ram"] == "8GB"


def test_first_item_screen(results):
    assert results[0]["screen"] == "13インチ"


def test_first_item_shop(results):
    assert results[0]["shopName"] == "Be-Stock"


def test_first_item_url_is_full(results):
    """URL should be absolute (https://kakaku.com/...)."""
    assert results[0]["itemUrl"].startswith("https://kakaku.com/")


# ── Second row: shop name with （店頭販売有） stripped ─────────────────────────

def test_shop_suffix_stripped(results):
    """'（店頭販売有）' should be removed from the shop name."""
    assert results[1]["shopName"] == "0799.jp"
    assert "（" not in results[1]["shopName"]


def test_second_item_price(results):
    assert results[1]["itemPrice"] == 20800


# ── Third row: OS is '無' (no OS) ─────────────────────────────────────────────

def test_no_os_row(results):
    assert results[2]["os"] == "無"
    assert results[2]["itemPrice"] == 22700


# ── Parametrized price extraction ─────────────────────────────────────────────

@pytest.mark.parametrize("idx,expected_price", [
    (0, 19400),
    (1, 20800),
    (2, 22700),
])
def test_prices(results, idx, expected_price):
    assert results[idx]["itemPrice"] == expected_price


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_empty_html_returns_empty_list():
    assert parse_kakaku_listings("") == []


def test_html_without_table_returns_empty_list():
    assert parse_kakaku_listings("<html><body><p>nothing</p></body></html>") == []


def test_scraped_at_is_set(results):
    for row in results:
        assert row["scraped_at"]
        assert "+09:00" in row["scraped_at"]  # JST timezone


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
        "cpu", "os", "ram", "storage", "screen",
    ]:
        assert col in df.columns


# ── _upsert_batch column mapping ──────────────────────────────────────────────

def test_after_full_rename_product_cols_present(results):
    df = (
        pl.from_dicts(results)
        .rename(_RENAME_MAP)
        .with_columns([
            pl.col("search_query").alias("model"),
            pl.col("screen").str.replace("インチ", "").cast(pl.Float64, strict=False).alias("display_size"),
        ])
    )
    assert set(_PRODUCT_COLS).issubset(set(df.columns))


def test_item_code_never_null(results):
    """itemCode is the upsert conflict key — must be non-empty for every row."""
    df = pl.from_dicts(results)
    assert df["itemCode"].null_count() == 0
    assert all(v != "" for v in df["itemCode"].to_list())


def test_display_size_parses_to_float(results):
    df = pl.from_dicts(results)
    sizes = df["screen"].str.replace("インチ", "").cast(pl.Float64, strict=False)
    assert sizes.null_count() == 0
    assert all(s > 0 for s in sizes.to_list())


# ── price_history readiness ───────────────────────────────────────────────────

def test_item_price_is_int_or_none(results):
    for row in results:
        assert row["itemPrice"] is None or isinstance(row["itemPrice"], int)


def test_price_history_fields_present(results):
    df = pl.from_dicts(results)
    for col in ["itemCode", "itemPrice", "search_query"]:
        assert col in df.columns


def test_no_null_item_codes_in_price_rows(results):
    """Every row with a non-null price must have a non-null itemCode."""
    for row in results:
        if row["itemPrice"] is not None:
            assert row["itemCode"]


# ── Playwright / live scrape ──────────────────────────────────────────────────

def test_kakaku_playwright_browser_installed():
    assert _PLAYWRIGHT_AVAILABLE, (
        "Playwright Chromium not found. "
        "Run: uv run playwright install chromium --with-deps"
    )


@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="Playwright browser not installed")
def test_kakaku_live_scrape_returns_items():
    from src.kakakucom_scrape import SEARCH_URLS, scrape_kakaku

    rows = asyncio.run(scrape_kakaku("L390", SEARCH_URLS["L390"]))
    assert len(rows) > 0
    assert all(r["source"] == "kakaku" for r in rows)
    assert all(isinstance(r["itemPrice"], int) for r in rows if r["itemPrice"] is not None)
    assert all(r["itemCode"] for r in rows)
