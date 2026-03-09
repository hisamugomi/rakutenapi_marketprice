# Scraper Authoring Guide

How to add a new marketplace scraper and wire it into the pipeline.

---

## 1. What a scraper must produce

Every scraper returns a `list[dict]`. Each dict is one product listing.

### Required fields (must be present in every row)

| Field | Type | Description |
|---|---|---|
| `itemCode` | `str` | Unique ID for this listing from the source site. Used as the upsert conflict key alongside `source`. Never empty. |
| `itemName` | `str` | Full product title. |
| `itemUrl` | `str` | Absolute URL to the listing (must start with `https://`). |
| `itemPrice` | `int \| None` | Price in yen as an integer. `None` if unparseable. |
| `shopName` | `str` | Seller/shop name. Strip parenthetical suffixes (e.g. `（店頭販売有）`). |
| `source` | `str` | Hardcoded string identifying the site (e.g. `"kakaku"`, `"sofmap"`). |
| `search_query` | `str` | The keyword used to find this item (e.g. `"L390"`). |
| `is_active` | `bool` | Always `True` when first scraped. |
| `scraped_at` | `str` | ISO 8601 timestamp in JST (`+09:00`). Use the snippet below. |

### Optional but recommended fields (map to products table columns)

| Field | Type | products column | Notes |
|---|---|---|---|
| `cpu` | `str` | `cpu` | e.g. `"Core i5"` |
| `os` | `str` | `os` | e.g. `"Windows 11 Pro"` or `"無"` |
| `ram` | `str` | `memory` | e.g. `"8GB"` — renamed in scraper.py |
| `storage` | `str` | `ssd` | e.g. `"256GB"` — renamed in scraper.py |
| `screen` | `str` | `display_size` | e.g. `"13インチ"` — parsed to float in scraper.py |

If the site doesn't provide a field, omit it — the upsert will store `NULL`.

### Timestamp snippet

```python
from datetime import datetime, timedelta, timezone
JST = timezone(timedelta(hours=9))
scraped_at = datetime.now(JST).isoformat()
```

---

## 2. File layout

```
src/
  yoursite_scrape.py          ← scraper module
tests/
  test_scrapers/
    test_yoursite_scraper.py  ← test module
```

### Minimum scraper structure

```python
# src/yoursite_scrape.py
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

SEARCH_URLS = {
    "L390": "https://example.com/search?q=L390",
    # ... more queries
}


def parse_yoursite_listings(html: str, search_query: str = "") -> list[dict]:
    """Pure parser — no I/O. Takes raw HTML, returns list of dicts."""
    scraped_at = datetime.now(JST).isoformat()
    results = []
    # ... parse html ...
    return results


async def scrape_yoursite(search_key: str, url: str) -> list[dict]:
    """Playwright fetcher for one search page."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("css-selector-for-results", timeout=15000)
        html = await page.content()
        await browser.close()
    return parse_yoursite_listings(html, search_query=search_key)


def run_yoursite_scraper() -> list[dict]:
    """Sync entry point — called by scraper.py."""
    all_results = []
    for key, url in SEARCH_URLS.items():
        results = asyncio.run(scrape_yoursite(key, url))
        all_results.extend(results)
    return all_results
```

---

## 3. Wiring into scraper.py

Add an import at the top:
```python
from src.yoursite_scrape import run_yoursite_scraper
```

Add a block in `run_scraper()` (before or after Sofmap):
```python
# ── YourSite ─────────────────────────────────────────────────────────────────
print("\n[yoursite] Scraping...")
yoursite_data = run_yoursite_scraper()
if yoursite_data:
    try:
        yoursite_pl = pl.from_dicts(yoursite_data).with_columns([
            pl.col("search_query").alias("model"),
            pl.col("ram").alias("memory"),          # only if field exists
            pl.col("storage").alias("ssd"),          # only if field exists
            pl.col("screen")
              .str.replace("インチ", "")
              .cast(pl.Float64, strict=False)
              .alias("display_size"),               # only if field exists
        ])
        _upsert_batch(supabase, yoursite_pl, "yoursite", now_jst)
    except Exception as e:
        print(f"  Error: {e}")
```

**How `_upsert_batch` works:**
1. Renames `itemCode→item_code`, `itemName→item_name`, `itemUrl→item_url`, `shopName→shop_name`
2. Filters to `_PRODUCT_COLS` and upserts into `products` on `(source, item_code)`
3. Looks up product IDs then inserts rows into `price_history` using `itemCode`, `itemPrice`, `search_query`
4. Marks any previously seen items from this source that weren't in this run as `is_active=False`

**Critical:** `itemCode` must be non-empty in every row. It is the conflict key for upsert. A blank `itemCode` causes a silent failure or duplicate insert.

---

## 4. Products table columns (`_PRODUCT_COLS`)

```python
_PRODUCT_COLS = [
    "item_code",    # from itemCode (required)
    "source",       # e.g. "kakaku" (required)
    "item_name",    # from itemName (required)
    "item_url",     # from itemUrl (required)
    "shop_name",    # from shopName (required)
    "search_query", # e.g. "L390" (required)
    "brand",        # e.g. "Lenovo" (optional)
    "model",        # e.g. "L390" — set to search_query if not parsed separately
    "cpu",          # e.g. "Core i5" (optional)
    "cpu_gen",      # e.g. "8th" (optional)
    "memory",       # e.g. "8GB" — from ram (optional)
    "ssd",          # e.g. "256GB" — from storage (optional)
    "hdd",          # e.g. "500GB" (optional)
    "os",           # e.g. "Windows 11 Pro" (optional)
    "display_size", # float, e.g. 13.0 — from screen (optional)
    "weight",       # e.g. "1.4kg" (optional)
    "bluetooth",    # bool or str (optional)
    "webcam",       # bool or str (optional)
    "usb_ports",    # str (optional)
    "is_active",    # bool (required)
    "last_seen_at", # added automatically by _upsert_batch
]
```

Columns not in this list are silently dropped. Missing columns are stored as `NULL`.

---

## 5. Price history table

`price_history` receives one row per product per scrape run:

```sql
price_history (
    product_id  uuid    -- looked up by item_code after upsert
    item_code   text    -- from itemCode
    source      text    -- e.g. "kakaku"
    price       int     -- from itemPrice (yen)
    scraped_at  timestamptz
    search_query text
)
```

Rows where `itemPrice is None` are skipped. Rows where `itemCode` isn't found in the products table are also skipped (this shouldn't happen if upsert ran first).

---

## 6. Required tests checklist

Create `tests/test_scrapers/test_yoursite_scraper.py` and cover all of these:

### A. Parser unit tests (no network, no browser)
Use a `SAMPLE_HTML` constant embedded in your scraper module (copy real HTML from the site).

- [ ] Returns the correct number of items from sample HTML
- [ ] All rows have the required keys (`itemCode`, `itemName`, `itemUrl`, `itemPrice`, `shopName`, `source`, `search_query`, `is_active`, `scraped_at`)
- [ ] `source` is your site string
- [ ] `is_active` is `True`
- [ ] `search_query` is propagated
- [ ] Spot-check first row: name, price, URL prefix, shop name
- [ ] `itemPrice` is `int` (not a string with `¥` or `,`)
- [ ] `scraped_at` contains `+09:00`
- [ ] Empty HTML returns `[]`
- [ ] HTML without the expected table/container returns `[]`

### B. Polars conversion tests
- [ ] `pl.from_dicts(results)` succeeds without error
- [ ] Resulting DataFrame has all required columns

### C. Column mapping tests (simulate what scraper.py does)
- [ ] After rename + `with_columns`, all `_PRODUCT_COLS` that should exist are present
- [ ] `itemCode` is never null or empty string
- [ ] `display_size` (if applicable) parses from the string format to a positive float

### D. Price history readiness
- [ ] `itemCode`, `itemPrice`, `search_query` all present in the DataFrame
- [ ] Every row with a non-null `itemPrice` has a non-null `itemCode`

### E. Playwright / live scrape
- [ ] Browser availability check (marks tests skip if not installed)
- [ ] Live smoke test: fetch one real URL, assert `len(results) > 0`, prices are ints

### Test template

```python
"""Tests for src/yoursite_scrape.py."""
from __future__ import annotations
import asyncio
import polars as pl
import pytest
from src.yoursite_scrape import SAMPLE_HTML, parse_yoursite_listings

REQUIRED_KEYS = {
    "itemCode", "itemName", "itemUrl", "itemPrice",
    "shopName", "source", "search_query", "is_active", "scraped_at",
}

@pytest.fixture
def results() -> list[dict]:
    return parse_yoursite_listings(SAMPLE_HTML, search_query="L390")

# ── Parser ────────────────────────────────────────────────────────────────────
def test_returns_correct_count(results):
    assert len(results) == <expected_count>

def test_all_rows_have_required_keys(results):
    for row in results:
        assert not (REQUIRED_KEYS - row.keys())

# ... (add field spot-checks, edge cases, etc.)

# ── Polars + mapping ──────────────────────────────────────────────────────────
def test_polars_conversion_succeeds(results):
    df = pl.from_dicts(results)
    assert isinstance(df, pl.DataFrame)

def test_item_code_never_null(results):
    df = pl.from_dicts(results)
    assert df["itemCode"].null_count() == 0
    assert all(v != "" for v in df["itemCode"].to_list())

# ── Playwright ────────────────────────────────────────────────────────────────
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright as _apw
    async def _check() -> bool:
        try:
            async with _apw() as p:
                b = await p.chromium.launch(); await b.close()
            return True
        except Exception:
            return False
    _PLAYWRIGHT_AVAILABLE = asyncio.run(_check())
except ImportError:
    pass

def test_playwright_browser_installed():
    assert _PLAYWRIGHT_AVAILABLE, "Run: uv run playwright install chromium --with-deps"

@pytest.mark.skipif(not _PLAYWRIGHT_AVAILABLE, reason="Playwright browser not installed")
def test_live_scrape_returns_items():
    from src.yoursite_scrape import SEARCH_URLS, scrape_yoursite
    rows = asyncio.run(scrape_yoursite("L390", SEARCH_URLS["L390"]))
    assert len(rows) > 0
    assert all(r["source"] == "yoursite" for r in rows)
    assert all(isinstance(r["itemPrice"], int) for r in rows if r["itemPrice"] is not None)
    assert all(r["itemCode"] for r in rows)
```

---

## 7. Common gotchas

| Problem | Fix |
|---|---|
| `itemCode` is empty | Extract from URL params (`sku=`, `jan=`) or fall back to a hash of the product name |
| Price has `¥` and `,` | `int(price_text.replace("¥","").replace(",",""))` |
| Anti-bot blocks live test | Mark it `@pytest.mark.skip` with a note; test the parser with `SAMPLE_HTML` only |
| `display_size` is `"13インチ"` | `.str.replace("インチ","").cast(pl.Float64, strict=False)` |
| Shop name has `（店頭販売有）` suffix | `shop_raw.split("（")[0].strip()` |
| Playwright browser not installed in CI | Add `uv run playwright install chromium --with-deps` to `scraper.yaml` |
| `bs4` vs `selectolax` | `bs4` is installed; `selectolax` is NOT — use `BeautifulSoup(html, "html.parser")` |
