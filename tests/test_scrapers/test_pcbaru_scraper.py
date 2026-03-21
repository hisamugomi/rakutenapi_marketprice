"""Tests for src/pcbaruscrape.py."""

from __future__ import annotations

import asyncio

import polars as pl
import pytest

from src.pcbaruscrape import (
    SAMPLE_DETAIL_HTML,
    SAMPLE_HTML,
    parse_pcbaru_detail,
    parse_pcbaru_listings,
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
    return parse_pcbaru_listings(SAMPLE_HTML, search_query="pcbaru_notebooks")


@pytest.fixture
def detail_specs() -> dict:
    return parse_pcbaru_detail(SAMPLE_DETAIL_HTML)


# ── Parser ────────────────────────────────────────────────────────────────────


def test_returns_correct_count(results: list[dict]) -> None:
    assert len(results) == 3


def test_all_rows_have_required_keys(results: list[dict]) -> None:
    for row in results:
        assert not (REQUIRED_KEYS - row.keys()), f"Missing keys: {REQUIRED_KEYS - row.keys()}"


def test_source_is_pcbaru(results: list[dict]) -> None:
    assert all(r["source"] == "pcbaru" for r in results)


def test_is_active_true(results: list[dict]) -> None:
    assert all(r["is_active"] is True for r in results)


def test_search_query_propagated(results: list[dict]) -> None:
    assert all(r["search_query"] == "pcbaru_notebooks" for r in results)


def test_first_row_spot_check(results: list[dict]) -> None:
    first = results[0]
    assert "ThinkPad L13" in first["itemName"]
    assert first["itemPrice"] == 38500
    assert "detail.php?id=17821" in first["itemUrl"]
    assert "福岡姪浜店" in first["shopName"]
    assert first["brand"] == "Lenovo"


def test_item_price_is_int(results: list[dict]) -> None:
    for r in results:
        assert isinstance(r["itemPrice"], int), f"Price should be int, got {type(r['itemPrice'])}"


def test_scraped_at_has_jst(results: list[dict]) -> None:
    for r in results:
        assert "+09:00" in r["scraped_at"], f"scraped_at should contain +09:00: {r['scraped_at']}"


def test_empty_html_returns_empty() -> None:
    assert parse_pcbaru_listings("") == []


def test_html_without_item_box_returns_empty() -> None:
    assert parse_pcbaru_listings("<html><body><p>No items here</p></body></html>") == []


def test_condition_parsed(results: list[dict]) -> None:
    assert results[0]["condition"] == "B"  # 使用感あるが良い状態
    assert results[2]["condition"] == "A"  # 使用感少なくきれいな状態


def test_os_parsed(results: list[dict]) -> None:
    assert results[0]["os"] is not None
    assert "Windows" in results[0]["os"]


def test_cpu_parsed(results: list[dict]) -> None:
    assert results[0]["cpu"] is not None
    assert "Core i5" in results[0]["cpu"]


def test_memory_parsed(results: list[dict]) -> None:
    assert results[0]["memory"] == "8GB"


def test_display_size_from_title(results: list[dict]) -> None:
    assert results[0]["display_size"] == 13.3
    assert results[1]["display_size"] == 15.6
    assert results[2]["display_size"] == 12.1


# ── Detail page parser ───────────────────────────────────────────────────────


def test_detail_sku(detail_specs: dict) -> None:
    assert detail_specs["sku"] == "2060601A0920"


def test_detail_cpu(detail_specs: dict) -> None:
    assert detail_specs["cpu"] == "Intel Core i5-10210U"


def test_detail_memory(detail_specs: dict) -> None:
    assert detail_specs["memory"] == "8GB"


def test_detail_ssd(detail_specs: dict) -> None:
    assert "256" in detail_specs["ssd"]


def test_detail_os(detail_specs: dict) -> None:
    assert "Windows11" in detail_specs["os"]


def test_detail_display_size(detail_specs: dict) -> None:
    assert detail_specs["display_size"] == 13.3


def test_detail_model_number(detail_specs: dict) -> None:
    assert detail_specs["model_number"] == "TP00114A"


def test_detail_condition(detail_specs: dict) -> None:
    assert detail_specs["condition"] == "B"


# ── Polars + mapping ─────────────────────────────────────────────────────────


def test_polars_conversion_succeeds(results: list[dict]) -> None:
    df = pl.from_dicts(results)
    assert isinstance(df, pl.DataFrame)


def test_polars_has_required_columns(results: list[dict]) -> None:
    df = pl.from_dicts(results)
    for col in ["itemCode", "itemName", "itemUrl", "itemPrice", "shopName", "source"]:
        assert col in df.columns, f"Missing column: {col}"


def test_item_code_never_null(results: list[dict]) -> None:
    df = pl.from_dicts(results)
    assert df["itemCode"].null_count() == 0
    assert all(v != "" for v in df["itemCode"].to_list())


def test_column_mapping(results: list[dict]) -> None:
    """Simulate what scraper.py does with column renaming."""
    df = pl.from_dicts(results).with_columns(
        [
            pl.col("search_query").alias("model"),
        ]
    )
    assert "model" in df.columns


# ── Price history readiness ──────────────────────────────────────────────────


def test_price_history_fields_present(results: list[dict]) -> None:
    df = pl.from_dicts(results)
    assert "itemCode" in df.columns
    assert "itemPrice" in df.columns
    assert "search_query" in df.columns


def test_price_with_non_null_code(results: list[dict]) -> None:
    df = pl.from_dicts(results)
    has_price = df.filter(pl.col("itemPrice").is_not_null())
    assert has_price["itemCode"].null_count() == 0


# ── Live scrape (Playwright not needed — httpx-based) ────────────────────────

_HTTPX_AVAILABLE = True
try:
    import httpx as _httpx_check
except ImportError:
    _HTTPX_AVAILABLE = False


@pytest.mark.skipif(not _HTTPX_AVAILABLE, reason="httpx not installed")
def test_live_scrape_returns_items() -> None:
    """Smoke test: fetch one real page and assert results."""
    from src.pcbaruscrape import LISTINGS_URL, _fetch_page

    async def _fetch() -> str:
        async with _httpx_check.AsyncClient(timeout=30.0) as client:
            return await _fetch_page(client, LISTINGS_URL)

    html = asyncio.run(_fetch())
    rows = parse_pcbaru_listings(html)
    assert len(rows) > 0, "Live scrape returned no items"
    assert all(r["source"] == "pcbaru" for r in rows)
    assert all(isinstance(r["itemPrice"], int) for r in rows if r["itemPrice"] is not None)
    assert all(r["itemCode"] for r in rows)
