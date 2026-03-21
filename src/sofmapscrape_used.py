"""
Scraper for https://used.sofmap.com — Sofmap used PC marketplace.

Scrapes laptop listings from the used.sofmap.com search results.
JS-rendered site — requires Playwright.

Title format:  ModelName ［CPU／RAM／Storage／Screen／OS］
Specs are extracted by splitting the bracket content on ／ (fullwidth slash).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

BASE_URL = "https://used.sofmap.com"
SEARCH_URL = (
    f"{BASE_URL}/r/item"
    "?categories1%5B%5D=pc"
    "&categories2%5B%5D=note"
    "&categories2%5B%5D=low-price-pc"
    "&rank%5B%5D=1&rank%5B%5D=2&rank%5B%5D=3&rank%5B%5D=4"
    "&q=PassMark%E3%82%B9%E3%82%B3%E3%82%A26000OVER"
    "&pc_sub1_6000over="
    "&jump=1"
)


# ── Brand cleaning ───────────────────────────────────────────────────────────

# Map Japanese brand labels to clean English names
_BRAND_MAP = {
    "Lenovo": "Lenovo",
    "レノボジャパン": "Lenovo",
    "FUJITSU": "Fujitsu",
    "富士通": "Fujitsu",
    "DELL": "Dell",
    "デル": "Dell",
    "hp": "HP",
    "エイチピー": "HP",
    "Panasonic": "Panasonic",
    "パナソニック": "Panasonic",
    "dynabook": "dynabook",
    "ダイナブック": "dynabook",
    "VAIO": "VAIO",
    "バイオ": "VAIO",
    "NEC": "NEC",
    "Apple": "Apple",
    "ASUS": "ASUS",
    "Microsoft": "Microsoft",
}


def _clean_brand(raw: str) -> str:
    """Extract clean brand name from e.g. 'Lenovo(レノボジャパン)'."""
    # Strip parenthetical suffix
    name = raw.split("(")[0].split("（")[0].strip()
    if name in _BRAND_MAP:
        return _BRAND_MAP[name]
    # Try the part inside parentheses
    for key, val in _BRAND_MAP.items():
        if key in raw:
            return val
    # Special case for その他メーカー — try to get brand from title later
    if "その他" in raw:
        return ""
    return name


# ── Spec extraction from bracket content ─────────────────────────────────────


def _parse_bracket_specs(title: str) -> dict:
    """Extract specs from ［CPU／RAM／Storage／Screen／OS］ in the title.

    Uses simple string splitting on ／ — no regex needed.
    """
    specs: dict = {
        "cpu": None,
        "memory": None,
        "ssd": None,
        "hdd": None,
        "display_size": None,
        "os": None,
    }

    # Find content between ［ and ］
    start = title.find("［")
    end = title.find("］")
    if start == -1 or end == -1:
        return specs

    bracket_content = title[start + 1 : end]
    parts = [p.strip() for p in bracket_content.split("／")]

    for part in parts:
        p = part.strip()
        if not p:
            continue

        # CPU — starts with Core, Ryzen, Celeron, AMD, Pentium, Atom, Xeon
        if any(
            p.startswith(kw)
            for kw in ("Core", "Ryzen", "Celeron", "AMD", "Pentium", "Atom", "Xeon")
        ):
            # Strip the clock speed part for a cleaner CPU field
            specs["cpu"] = p.split("(")[0].split("（")[0].strip()
            continue

        # RAM — just a number + GB (e.g. "8GB", "16GB")
        if p.endswith("GB") and p[:-2].isdigit():
            specs["memory"] = p
            continue

        # SSD
        if p.startswith("SSD"):
            specs["ssd"] = p.replace("SSD", "").strip()
            continue

        # HDD
        if p.startswith("HDD"):
            specs["hdd"] = p.replace("HDD", "").strip()
            continue

        # Screen — contains インチ
        if "インチ" in p:
            # Extract the numeric part
            num = p.replace("インチワイド", "").replace("インチ", "").strip()
            try:
                specs["display_size"] = float(num)
            except ValueError:
                pass
            continue

        # OS — contains Windows, Linux, macOS, Chrome
        if any(kw in p for kw in ("Windows", "Linux", "macOS", "Chrome")):
            specs["os"] = p
            continue

    return specs


# ── HTML parser ──────────────────────────────────────────────────────────────


def parse_sofmap_used_listings(
    html: str,
    search_query: str = "sofmap_used_notebooks",
) -> list[dict]:
    """Parse used.sofmap.com listing page HTML.

    Args:
        html: Raw HTML of a used.sofmap.com search results page.
        search_query: Label stored on each row.

    Returns:
        List of dicts, one per listing.
    """
    soup = BeautifulSoup(html, "html.parser")
    scraped_at = datetime.now(JST).isoformat()
    results: list[dict] = []

    for li in soup.select("ul.sys-display-item li"):
        try:
            anchor = li.find("a")
            if not anchor:
                continue

            href = anchor.get("href", "")
            if not href:
                continue

            # ── Item ID ──────────────────────────────────────────────────
            # Individual items: /r/item/2133072435673
            # Aggregated items: /r/item?...&jan=2000453972020&...
            is_aggregated = "sys-aggregation-item" in (anchor.get("class") or [])

            if "/r/item/" in href and not is_aggregated:
                item_id = href.rstrip("/").split("/")[-1]
            else:
                # Aggregated — extract jan= param
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                jan_list = qs.get("jan", [])
                item_id = jan_list[0] if jan_list else ""

            if not item_id:
                continue

            item_url = f"{BASE_URL}{href}" if href.startswith("/") else href

            # ── Brand ────────────────────────────────────────────────────
            brand_el = anchor.select_one("p.sys-maker")
            brand_raw = brand_el.get_text(strip=True) if brand_el else ""
            brand = _clean_brand(brand_raw)

            # ── Name ─────────────────────────────────────────────────────
            name_el = anchor.select_one("p.sys-name") or anchor.select_one("p.sys-short-name")
            item_name = name_el.get_text(strip=True) if name_el else ""

            # ── Price ────────────────────────────────────────────────────
            price_el = anchor.select_one("span.sys-price")
            item_price = None
            if price_el:
                price_text = price_el.get_text(strip=True).replace(",", "").replace("～", "")
                if price_text.isdigit():
                    item_price = int(price_text)

            # ── Condition rank ───────────────────────────────────────────
            rank_el = anchor.select_one("strong.sys-rank")
            condition = rank_el.get_text(strip=True) if rank_el else None

            # ── Shop ─────────────────────────────────────────────────────
            shop_el = anchor.select_one("dd.sys-handled-shop-name")
            shop_name = shop_el.get_text(strip=True) if shop_el else "リコレ"

            # ── Specs from bracket content ───────────────────────────────
            specs = _parse_bracket_specs(item_name)

            results.append(
                {
                    "itemCode": item_id,
                    "itemName": item_name,
                    "itemPrice": item_price,
                    "itemUrl": item_url,
                    "shopName": shop_name,
                    "source": "sofmap_used",
                    "search_query": search_query,
                    "is_active": True,
                    "scraped_at": scraped_at,
                    "brand": brand or None,
                    "condition": condition,
                    "cpu": specs["cpu"],
                    "memory": specs["memory"],
                    "ssd": specs["ssd"],
                    "hdd": specs["hdd"],
                    "display_size": specs["display_size"],
                    "os": specs["os"],
                }
            )
        except Exception as e:
            print(f"[sofmap_used] Error parsing item: {e}")
            continue

    return results


# ── Playwright fetcher ───────────────────────────────────────────────────────


async def _get_total(page) -> int:
    """Read total hit count from the page."""
    el = await page.locator("span.sys-total").first.inner_text()
    return int(el.replace(",", "").strip())


async def scrape_sofmap_used_page(url: str) -> str:
    """Fetch one page of used.sofmap.com and return rendered HTML."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, timeout=60_000, wait_until="domcontentloaded")
        await page.wait_for_selector("ul.sys-display-item", timeout=15_000)
        html = await page.content()
        await browser.close()
    return html


def run_sofmap_used_scraper(max_pages: int | None = None) -> list[dict]:
    """Sync entry point — scrapes used.sofmap.com notebook listings.

    Args:
        max_pages: Maximum pages to scrape (None = all). ~30 items/page.

    Returns:
        List of item dicts.
    """
    # First page — get total count
    print("[sofmap_used] Fetching page 1...")
    html = asyncio.run(scrape_sofmap_used_page(SEARCH_URL))
    soup = BeautifulSoup(html, "html.parser")
    total_el = soup.select_one("span.sys-total")
    total = int(total_el.get_text(strip=True).replace(",", "")) if total_el else 0

    items_per_page = 30  # used.sofmap.com default
    total_pages = (total + items_per_page - 1) // items_per_page
    pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages

    print(f"[sofmap_used] Total: {total} items, {total_pages} pages, scraping: {pages_to_scrape}")

    all_results = parse_sofmap_used_listings(html)
    print(f"[sofmap_used] Page 1: {len(all_results)} items")

    for page_num in range(2, pages_to_scrape + 1):
        delay = 3.0
        print(f"[sofmap_used] Waiting {delay}s...")
        time.sleep(delay)

        url = f"{SEARCH_URL}&page={page_num}"
        print(f"[sofmap_used] Page {page_num}/{pages_to_scrape}...")
        page_html = asyncio.run(scrape_sofmap_used_page(url))
        results = parse_sofmap_used_listings(page_html)
        print(f"[sofmap_used] Page {page_num}: {len(results)} items")
        all_results.extend(results)

    print(f"[sofmap_used] Total scraped: {len(all_results)}")
    return all_results


# ── Sample HTML (used in tests) ──────────────────────────────────────────────
SAMPLE_HTML = """<div class="item-list list sys-list" id="search-result-div">
<div class="total-hit"><p><span class="sys-total">448</span>点</p></div>
<ul class="sys-display-item list-block">

<li><a href="/r/item/2133072435673" target="_blank">
  <div class="item-wrap clearfix"><div class="product-info-wrap">
    <div class="img-area"><figure>
      <img alt="ideapad S540" class="sys-image" src="https://image.sofmap.com/images/product/large/2133072435673_1.jpg">
      <span class="rank-icon sys-rank-icon second"><strong class="sys-rank">B</strong>ランク</span>
    </figure></div>
    <div class="info-area"><div class="detail-area">
      <p class="brand sys-maker">Lenovo(レノボジャパン)</p>
      <p class="name sys-name">ideapad S540 81NF000VJP ［Core-i5-10210U (1.6GHz)／8GB／SSD256GB／14インチワイド／Windows11 Home(アップグレード済み)］</p>
      <p class="spec-hightlight sys-spec-highlight">Core i5 10210U (1.6GHz) | 14インチワイド | Windows 11 Home(アップグレード済み)</p>
    </div><div class="price-area"><p class="item-price">
      <span class="price-mark">¥</span><span class="sys-price price">40,980</span><span class="tax-included">(税込)</span>
    </p></div></div>
  </div><div class="shop-info-area sys-handled-shop"><dl>
    <dt><span class="shop-info-headding">取扱店舗</span></dt>
    <dd class="sys-handled-shop-name">AKIBA パソコン・デジタル館</dd>
  </dl></div></div>
</a></li>

<li><a href="/r/item/2133071291980" target="_blank">
  <div class="item-wrap clearfix"><div class="product-info-wrap">
    <div class="img-area"><figure>
      <img alt="LIFEBOOK AH53" class="sys-image" src="https://image.sofmap.com/images/product/large/2133071291980_1.jpg">
      <span class="rank-icon sys-rank-icon second"><strong class="sys-rank">C</strong>ランク</span>
    </figure></div>
    <div class="info-area"><div class="detail-area">
      <p class="brand sys-maker">FUJITSU(富士通)</p>
      <p class="name sys-name">格安安心パソコン LIFEBOOK AH53／A3 FMVA53A3B シャイニーブラック 〔Windows 10〕 ［Core-i7-6700HQ (2.6GHz)／16GB／HDD1TB／15.6インチワイド／Windows10 Home(64ビット)］</p>
      <p class="spec-hightlight sys-spec-highlight">Core i7 6700HQ (2.6GHz) | 15.6インチワイド | Windows 10 Home(64ビット)</p>
    </div><div class="price-area"><p class="item-price">
      <span class="price-mark">¥</span><span class="sys-price price">24,980</span><span class="tax-included">(税込)</span>
    </p></div></div>
  </div><div class="shop-info-area sys-handled-shop"><dl>
    <dt><span class="shop-info-headding">取扱店舗</span></dt>
    <dd class="sys-handled-shop-name">AKIBA パソコン・デジタル館</dd>
  </dl></div></div>
</a></li>

<li><a href="/r/item/2133072078566" target="_blank">
  <div class="item-wrap clearfix"><div class="product-info-wrap">
    <div class="img-area"><figure>
      <img alt="Inspiron 3593" class="sys-image" src="https://image.sofmap.com/images/product/large/2133072078566_1.jpg">
      <span class="rank-icon sys-rank-icon second"><strong class="sys-rank">B</strong>ランク</span>
    </figure></div>
    <div class="info-area"><div class="detail-area">
      <p class="brand sys-maker">DELL(デル)</p>
      <p class="name sys-name">Inspiron 3593 〔Windows 10〕 ［Core-i5-1035G1 (1GHz)／8GB／SSD512GB／15.6インチワイド／Windows10 Home(64ビット)］</p>
      <p class="spec-hightlight sys-spec-highlight">Core i5 1035G1 (1GHz) | 15.6インチワイド | Windows 10 Home(64ビット)</p>
    </div><div class="price-area"><p class="item-price">
      <span class="price-mark">¥</span><span class="sys-price price">39,980</span><span class="tax-included">(税込)</span>
    </p></div></div>
  </div><div class="shop-info-area sys-handled-shop"><dl>
    <dt><span class="shop-info-headding">取扱店舗</span></dt>
    <dd class="sys-handled-shop-name">川越店</dd>
  </dl></div></div>
</a></li>

<li><a href="/r/item?_matome=0&amp;categories1%5B%5D=pc&amp;jan=2000453972020&amp;_returnto=%2Fr%2Fitem" class="sys-aggregation-item">
  <div class="item-wrap clearfix"><div class="product-info-wrap">
    <div class="img-area"><figure>
      <img src="https://image.sofmap.com/images/product/large/2133071162358_1.jpg" alt="VAIO Pro PG" class="sys-image">
    </figure></div>
    <div class="info-area"><div class="detail-area">
      <p class="brand sys-maker">VAIO(バイオ)</p>
      <p class="name sys-short-name">VAIO Pro PG VJPG13C11N ［Core-i5-1035G1 (1GHz)／8GB／SSD256GB／13.3インチワイド／Windows11 Pro MAR］</p>
    </div><div class="price-area"><p class="item-price">
      <span class="sys-symbol-max_price_tax_include"></span><span class="price-mark">¥</span><span class="sys-price price">42,980</span><span class="sys-symbol-min_price_tax_include">～</span><span class="tax-included">(税込)</span>
    </p><p class="stock-btn">同一商品：<span class="sys-count">3</span>点</p></div></div>
  </div></div>
</a></li>

</ul></div>"""


if __name__ == "__main__":
    results = run_sofmap_used_scraper(max_pages=2)

    import polars as pl

    df = pl.DataFrame(results)
    df.write_csv("data/sofmap_used_scraped.csv")
    print(f"Saved {len(df)} items to sofmap_used_scraped.csv")
