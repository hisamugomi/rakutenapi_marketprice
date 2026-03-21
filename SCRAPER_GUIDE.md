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

---

## 8. Best practices

### Prefer simple string splitting over regex

Japanese used-PC sites follow predictable title formats. Split on delimiters first; only reach for regex if splitting genuinely can't handle it.

**Example — Sofmap used titles:**
```
ideapad S540 ［Core-i5-10210U (1.6GHz)／8GB／SSD256GB／14インチワイド／Windows11 Pro MAR］
```

Parse with splits, not regex:
```python
# 1. Extract bracket content
start, end = title.find("［"), title.find("］")
parts = title[start+1:end].split("／")   # fullwidth slash ／

# 2. Classify each part by simple keyword checks
for part in parts:
    p = part.strip()
    if p.startswith(("Core", "Ryzen", "Celeron")):
        specs["cpu"] = p.split("(")[0].strip()       # drop "(1.6GHz)"
    elif p.endswith("GB") and p[:-2].isdigit():
        specs["memory"] = p                           # "8GB"
    elif p.startswith("SSD"):
        specs["ssd"] = p.replace("SSD", "").strip()   # "256GB"
    elif p.startswith("HDD"):
        specs["hdd"] = p.replace("HDD", "").strip()
    elif "インチ" in p:
        specs["display_size"] = float(p.replace("インチワイド", "").replace("インチ", ""))
    elif any(kw in p for kw in ("Windows", "Linux", "macOS")):
        specs["os"] = p
```

**Why this is better than regex:**
- Easier to read and debug — each `elif` is one field
- Delimiter-based splitting matches how the data is actually structured
- No risk of catastrophic backtracking or subtle regex bugs
- Adding a new field = adding one `elif` branch

### Always get sample HTML first

**Before writing any parsing code**, fetch and save a real HTML page from the target site. This is the very first step for any new scraper.

```python
# Quick one-off to grab sample HTML (run in terminal, not in the scraper itself)
uv run python -c "
import asyncio
from playwright.async_api import async_playwright

async def fetch():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://example.com/search', timeout=60000)
        await page.wait_for_selector('div.product-list', timeout=15000)  # wait for JS
        html = await page.content()
        await browser.close()
        with open('/tmp/sitename_sample.html', 'w') as f:
            f.write(html)
        print(f'Saved {len(html)} chars')

asyncio.run(fetch())
"
```

Then inspect it to understand the HTML structure before writing selectors:
```python
uv run python -c "
from bs4 import BeautifulSoup
with open('/tmp/sitename_sample.html') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')
items = soup.select('div.product')  # try different selectors
print(f'Found {len(items)} items')
for i, item in enumerate(items[:3]):
    print(f'--- Item {i} ---')
    print(str(item)[:500])
"
```

**Why this matters:**
- You see the real DOM, not what the docs say it should be
- JS-rendered sites often have different structure than view-source shows
- You can pick 3–5 representative items for `SAMPLE_HTML` from real data
- Saves time vs. guessing selectors and debugging why they don't match

### Separate parser from fetcher

Every scraper module should have two clear layers:

1. **`parse_*_listings(html, search_query) -> list[dict]`** — pure function, no I/O, no browser. Takes raw HTML string, returns structured data. This is what tests exercise.
2. **`scrape_*_page(url) -> str`** — async Playwright fetcher that returns raw HTML. Thin wrapper.

This separation means:
- 95% of tests run instantly against `SAMPLE_HTML` (no browser needed)
- The parser is reusable if you switch from Playwright to httpx later
- Debugging is easier — you can save HTML to a file and re-parse it

### Embed SAMPLE_HTML in the scraper module

Put a `SAMPLE_HTML` constant directly in the scraper `.py` file (not in a separate fixture file). Keep it small — 3–5 representative items covering the main variations:
- A typical item with all fields
- An item with HDD instead of SSD (or other storage variant)
- An aggregated/bundle item if the site has them
- An edge case (missing field, unusual brand)

Tests import `SAMPLE_HTML` from the scraper module, so the test data lives next to the parsing code it tests.

### Brand name cleaning

Japanese sites append the Japanese company name in parentheses. Always strip it and normalize:

```python
_BRAND_MAP = {
    "lenovo":   "Lenovo",
    "fujitsu":  "Fujitsu",
    "hp":       "HP",
    "dell":     "Dell",
    "nec":      "NEC",
    "vaio":     "VAIO",
    "panasonic":"Panasonic",
    "toshiba":  "Toshiba",
    "dynabook": "Dynabook",
}

def _clean_brand(raw: str) -> str:
    base = raw.split("(")[0].split("（")[0].strip()   # strip Japanese parens too
    return _BRAND_MAP.get(base.lower(), base)
```

Map `その他メーカー` ("other manufacturer") to `""` — it carries no useful brand info.

### Handle multiple listing types

Some sites mix individual items and aggregated/bundle listings on the same page. Check for both:
- **Individual items:** ID from URL path (e.g. `/r/item/2133072435673`)
- **Aggregated items:** ID from URL query param (e.g. `?jan=2000453972020`)
- Aggregated items typically lack per-item fields like `condition` — set those to `None`

### Price cleaning

Always strip currency symbols AND fullwidth variants before `int()`:
```python
price_text = raw.replace("¥", "").replace("￥", "").replace(",", "").replace("（税込）", "").strip()
item_price = int(price_text) if price_text.isdigit() else None
```

### Anti-detection for Playwright scrapers

For JS-rendered sites that check for bots:
- Rotate user agents from a small list (3–4 real browser strings)
- Randomize viewport dimensions slightly
- Set `locale="ja-JP"` and `timezone_id="Asia/Tokyo"`
- Patch `navigator.webdriver` to `undefined`
- Add small random delays between pages (`random.uniform(2.0, 5.0)`)
- Use `--no-sandbox` and `--disable-blink-features=AutomationControlled` launch args

### Deduplication

`_upsert_batch` in scraper.py uses `(source, item_code)` as the conflict key. If the same `itemCode` appears multiple times in one scrape run (e.g. from overlapping search queries), deduplicate before upserting:
```python
products_df = products_df.unique(subset=["item_code"], keep="first")
```

### robots.txt compliance

Before writing a new scraper, check the target site's `robots.txt`. If the paths you're scraping are disallowed, reconsider or contact the site owner. Document the check in your PR description.
