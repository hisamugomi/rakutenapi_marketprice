"""
Scraper for https://www.pcwrap.com — used PC retailer.
Scrapes laptop listings paginated via &o={offset} (16 items/page).

Extracted fields per listing:
  itemCode, itemName, itemUrl, itemPrice, shopName, source, search_query,
  is_active, scraped_at, brand, model, os, cpu, memory, ssd, hdd,
  display_size, condition
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime, timedelta, timezone
from math import ceil

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

BASE_URL = "https://www.pcwrap.com"
LISTINGS_URL = f"{BASE_URL}/item/index/?category1=2&nojunk=true"
ITEMS_PER_PAGE = 16

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def _parse_specs(subspec_texts: list[str]) -> dict:
    """Parse spec fields from a list of subspec text strings."""
    specs: dict = {
        "ram_gb": None,
        "storage_gb": None,
        "storage_type": None,
        "screen_size": None,
        "condition": None,
    }

    for text in subspec_texts:
        t = text.strip()

        m = re.search(r"メモリ\s*(\d+)\s*GB", t)
        if m:
            specs["ram_gb"] = int(m.group(1))
            continue

        m = re.search(r"(SSD|HDD|NVMe)\s*(\d+)\s*GB", t, re.IGNORECASE)
        if m:
            specs["storage_type"] = m.group(1).upper()
            specs["storage_gb"] = int(m.group(2))
            continue

        m = re.search(r"([\d.]+)\s*インチ", t)
        if m:
            specs["screen_size"] = float(m.group(1))
            continue

        m = re.search(r"状態ランク[：:]\s*(\S+)", t)
        if m:
            specs["condition"] = m.group(1)
            continue

    return specs


def parse_pcwrap_listings(html: str, search_query: str = "pcwrap_notebooks") -> list[dict]:
    """Parse a PCWrap listing page.

    Args:
        html: Raw HTML of a pcwrap.com listings page.
        search_query: Label stored on each row.

    Returns:
        List of dicts, one per listing.
    """
    soup = BeautifulSoup(html, "html.parser")
    scraped_at = datetime.now(JST).isoformat()
    results = []

    for li in soup.select("ul.list-item li"):
        try:
            anchor = li.find("a")
            if not anchor:
                continue

            href = anchor.get("href", "")
            if not href:
                continue
            m = re.search(r"item/detail/(\d+)", href)
            item_id = m.group(1) if m else href
            item_url = f"{BASE_URL}/{href.lstrip('/')}"

            # Brand and model from first two <strong> inside subspec spans
            strong_tags = anchor.select("span.subspec strong")
            brand = strong_tags[0].get_text(strip=True) if len(strong_tags) > 0 else None
            model = strong_tags[1].get_text(strip=True) if len(strong_tags) > 1 else None
            item_name = f"{brand} {model}".strip() if (brand or model) else item_id

            # Price from <p> containing ￥
            price_p = next(
                (p for p in anchor.find_all("p") if "￥" in p.get_text()), None
            )
            item_price = None
            if price_p:
                price_text = price_p.get_text().replace("￥", "").replace(",", "").strip()
                price_match = re.search(r"\d+", price_text)
                item_price = int(price_match.group()) if price_match else None

            # All subspec text blocks for spec parsing
            subspec_texts = [el.get_text(strip=True) for el in anchor.select("span.subspec")]
            specs = _parse_specs(subspec_texts)

            # OS and CPU via keyword scan of subspec texts
            os_val = None
            cpu_val = None
            for t in subspec_texts:
                if os_val is None and any(kw in t for kw in ["Windows", "Linux", "Chrome OS", "macOS"]):
                    os_val = t
                if cpu_val is None and any(kw in t for kw in ["Core", "Ryzen", "Celeron", "Pentium", "Atom", "Xeon"]):
                    cpu_val = t

            # Map storage to ssd / hdd columns
            ssd: str | None = None
            hdd: str | None = None
            if specs["storage_gb"]:
                storage_str = f"{specs['storage_gb']}GB"
                if specs["storage_type"] == "HDD":
                    hdd = storage_str
                else:
                    ssd = storage_str

            # Sold-out check
            is_active = anchor.find("img", alt="完売しました") is None

            results.append({
                "itemCode":     item_id,
                "itemName":     item_name,
                "itemPrice":    item_price,
                "itemUrl":      item_url,
                "shopName":     "PCwrap",
                "source":       "pcwrap",
                "search_query": search_query,
                "is_active":    is_active,
                "scraped_at":   scraped_at,
                "brand":        brand,
                "model":        model,
                "os":           os_val,
                "cpu":          cpu_val,
                "memory":       f"{specs['ram_gb']}GB" if specs["ram_gb"] else None,
                "ssd":          ssd,
                "hdd":          hdd,
                "display_size": specs["screen_size"],
                "condition":    specs["condition"],
            })
        except Exception as e:
            print(f"[pcwrap] Error parsing item: {e}")
            continue

    return results


async def _new_stealth_page(browser):
    """Create a new page with anti-detection headers and JS patches."""
    ua = random.choice(USER_AGENTS)
    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": random.randint(1280, 1920), "height": random.randint(720, 1080)},
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        extra_http_headers={
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return await context.new_page()


async def _get_total_listings(url: str) -> int:
    """Return total number of listings from the sort-left count element."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=LAUNCH_ARGS)
        page = await _new_stealth_page(browser)
        await page.goto(url=url, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        raw_num = await page.locator("div.sort-left b").first.inner_text()
        await browser.close()
        return int(raw_num.replace(",", "").strip())


async def scrape_pcwrap(url: str) -> list[dict]:
    """Fetch one PCWrap listing page and parse it."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=LAUNCH_ARGS)
        page = await _new_stealth_page(browser)
        await page.goto(url=url, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        await page.mouse.move(random.randint(200, 800), random.randint(200, 600))
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.4)")
        await asyncio.sleep(random.uniform(0.5, 1.2))
        html = await page.content()
        await browser.close()
    return parse_pcwrap_listings(html)


def run_pcwrap_scraper(max_pages: int | None = None) -> list[dict]:
    """Sync entry point — scrapes all pages of PCWrap laptop listings.

    Args:
        max_pages: Maximum number of pages to scrape (None = all).

    Returns:
        List of item dicts.
    """
    total = asyncio.run(_get_total_listings(LISTINGS_URL))
    total_pages = ceil(total / ITEMS_PER_PAGE)
    pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages

    print(f"[pcwrap] Total listings: {total}, pages: {total_pages}, scraping: {pages_to_scrape}")

    all_results: list[dict] = []

    for page_num in range(1, pages_to_scrape + 1):
        if page_num > 1:
            delay = random.uniform(4.0, 9.0)
            print(f"[pcwrap] Waiting {delay:.1f}s...")
            time.sleep(delay)

        offset = (page_num - 1) * ITEMS_PER_PAGE
        url = LISTINGS_URL if page_num == 1 else f"{LISTINGS_URL}&o={offset}"
        print(f"[pcwrap] Page {page_num}/{pages_to_scrape}: {url}")

        results = asyncio.run(scrape_pcwrap(url))
        print(f"[pcwrap] Found {len(results)} items on page {page_num}")
        all_results.extend(results)

    print(f"[pcwrap] Total scraped: {len(all_results)}")
    return all_results


# ── Sample HTML (used in tests) ───────────────────────────────────────────────
# Minimal representative HTML matching the pcwrap.com listing structure.
SAMPLE_HTML = """<div class="sort-left"><b>48</b>件</div>
<ul class="list-item">

  <li>
    <a href="/item/detail/100123">
      <span class="subspec"><strong>Panasonic</strong></span>
      <span class="subspec"><strong>Let's note CF-SV7RDYVS</strong></span>
      <span class="subspec">Windows 11 Pro</span>
      <span class="subspec">Core i5-8350U 1.7GHz</span>
      <span class="subspec">メモリ 8GB</span>
      <span class="subspec">SSD 256GB</span>
      <span class="subspec">12.1インチ</span>
      <span class="subspec">状態ランク：A</span>
      <p>￥29,800（税込）</p>
    </a>
  </li>

  <li>
    <a href="/item/detail/100456">
      <span class="subspec"><strong>Lenovo</strong></span>
      <span class="subspec"><strong>ThinkPad X1 Carbon 6th</strong></span>
      <span class="subspec">Windows 10 Pro</span>
      <span class="subspec">Core i7-8550U 1.8GHz</span>
      <span class="subspec">メモリ 16GB</span>
      <span class="subspec">SSD 512GB</span>
      <span class="subspec">14インチ</span>
      <span class="subspec">状態ランク：B</span>
      <p>￥38,500（税込）</p>
    </a>
  </li>

  <li>
    <a href="/item/detail/100789">
      <span class="subspec"><strong>Dell</strong></span>
      <span class="subspec"><strong>Latitude 5490</strong></span>
      <span class="subspec">Windows 11 Pro</span>
      <span class="subspec">Core i5-8250U 1.6GHz</span>
      <span class="subspec">メモリ 8GB</span>
      <span class="subspec">HDD 500GB</span>
      <span class="subspec">14インチ</span>
      <span class="subspec">状態ランク：C</span>
      <p>￥14,800（税込）</p>
    </a>
  </li>

</ul>"""


if __name__ == "__main__":
    results = run_pcwrap_scraper(max_pages=2)

    import polars as pl

    df = pl.DataFrame(results)
    df.write_csv("data/pcwrap_scraped.csv")
    print(f"Saved {len(df)} items to pcwrap_scraped.csv")
