"""
Scraper for https://www.pcwrap.com — used PC retailer.
Scrapes laptop listings paginated via &o={offset} (16 items/page).
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from datetime import datetime, timedelta, timezone
from math import ceil

from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

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


def _random_delay(min_s: float = 1.5, max_s: float = 4.0) -> None:
    time.sleep(random.uniform(min_s, max_s))


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
    # Hide webdriver flag
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = await context.new_page()
    return page


async def findmaxlisting(url: str) -> int:
    """Return total number of listings from the sort-left count element."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=LAUNCH_ARGS)
        page = await _new_stealth_page(browser)
        await page.goto(url=url, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        raw_num = await page.locator("div.sort-left b").first.inner_text()
        await browser.close()
        clean_num = int(raw_num.replace(",", "").strip())
        return clean_num


def _parse_specs(subspec_texts: list[str]) -> dict:
    """Parse spec fields from list of subspec text strings."""
    specs: dict = {
        "os": None,
        "cpu": None,
        "ram_gb": None,
        "storage_gb": None,
        "storage_type": None,
        "gpu": None,
        "screen_size": None,
        "condition": None,
        "stock": None,
    }

    for text in subspec_texts:
        t = text.strip()

        # RAM
        m = re.search(r"メモリ\s*(\d+)\s*GB", t)
        if m:
            specs["ram_gb"] = int(m.group(1))
            continue

        # Storage
        m = re.search(r"(SSD|HDD|NVMe)\s*(\d+)\s*GB", t, re.IGNORECASE)
        if m:
            specs["storage_type"] = m.group(1).upper()
            specs["storage_gb"] = int(m.group(2))
            continue

        # Screen size
        m = re.search(r"([\d.]+)\s*インチ", t)
        if m:
            specs["screen_size"] = float(m.group(1))
            continue

        # Condition rank
        m = re.search(r"状態ランク[：:]\s*(\S+)", t)
        if m:
            specs["condition"] = m.group(1)
            continue

        # Stock
        m = re.search(r"在庫数[：:]\s*(\d+)", t)
        if m:
            specs["stock"] = int(m.group(1))
            continue

    return specs


async def scrape_pcwrap(url: str) -> list[dict]:
    """Scrape a single PCWrap listing page and return items as dicts."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=LAUNCH_ARGS)
        page = await _new_stealth_page(browser)
        await page.goto(url=url, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(random.uniform(1.5, 3.0))

        # Simulate human scroll
        await page.mouse.move(random.randint(200, 800), random.randint(200, 600))
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await page.evaluate("window.scrollBy(0, window.innerHeight * 0.4)")
        await asyncio.sleep(random.uniform(0.5, 1.2))

        items = await page.locator("ul.list-item li").all()
        results = []
        scraped_at = datetime.now(JST).isoformat()

        for item in items:
            try:
                anchor = item.locator("a").first

                # Item URL and ID
                href = await anchor.get_attribute("href")
                if not href:
                    continue
                m = re.search(r"item/detail/(\d+)", href)
                item_id = m.group(1) if m else href
                item_url = f"https://www.pcwrap.com/{href.lstrip('/')}"

                # Brand and model from first two strong tags inside subspec spans
                strong_tags = await anchor.locator("span.subspec strong").all()
                brand = (await strong_tags[0].inner_text()).strip() if len(strong_tags) > 0 else None
                model = (await strong_tags[1].inner_text()).strip() if len(strong_tags) > 1 else None
                item_name = f"{brand} {model}".strip() if brand or model else item_id

                # Price from <p> containing ￥
                price_raw = await anchor.locator("p").filter(has_text="￥").first.inner_text()
                price_text = price_raw.replace("￥", "").replace(",", "").strip()
                # Take first numeric run (handles trailing text)
                price_match = re.search(r"\d+", price_text)
                item_price = int(price_match.group()) if price_match else None

                # All subspec text blocks for spec parsing
                subspec_els = await anchor.locator("span.subspec").all()
                subspec_texts = [await el.inner_text() for el in subspec_els]
                specs = _parse_specs(subspec_texts)

                # OS and CPU: first subspec after <hr class="dashed"> separators
                # We fall back to scanning subspec texts for common keywords
                os_val = None
                cpu_val = None
                for t in subspec_texts:
                    t_clean = t.strip()
                    if os_val is None and any(kw in t_clean for kw in ["Windows", "Linux", "Chrome OS", "macOS"]):
                        os_val = t_clean
                    if cpu_val is None and any(kw in t_clean for kw in ["Core", "Ryzen", "Celeron", "Pentium", "Atom", "Xeon"]):
                        cpu_val = t_clean

                # is_active: no "完売しました" image
                sold_out_img = await anchor.locator('img[alt="完売しました"]').count()
                is_active = sold_out_img == 0

                results.append({
                    "itemCode": item_id,
                    "itemName": item_name,
                    "itemPrice": item_price,
                    "itemUrl": item_url,
                    "scraped_at": scraped_at,
                    "search_query": "pcwrap_notebooks",
                    "source": "pcwrap",
                    "is_active": is_active,
                    "brand": brand,
                    "os": os_val,
                    "cpu": cpu_val,
                    "ram_gb": specs["ram_gb"],
                    "storage_gb": specs["storage_gb"],
                    "storage_type": specs["storage_type"],
                    "gpu": specs["gpu"],
                    "screen_size": specs["screen_size"],
                    "condition": specs["condition"],
                })
            except Exception as e:
                print(f"[pcwrap] Error parsing item: {e}")
                continue

        await browser.close()
        return results


def run_pcwrap_scraper(max_pages: int | None = None) -> list[dict]:
    """
    Sync entry point — scrapes all pages of PCWrap laptop listings.

    Args:
        max_pages: Maximum number of pages to scrape (None = all pages).

    Returns:
        List of item dicts.
    """
    base_url = "https://www.pcwrap.com/item/index/?category1=2&nojunk=true"
    items_per_page = 16

    # Get total listing count
    total = asyncio.run(findmaxlisting(base_url))
    total_pages = ceil(total / items_per_page)
    pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages

    print(f"[pcwrap] Total listings: {total}")
    print(f"[pcwrap] Total pages: {total_pages}")
    print(f"[pcwrap] Scraping: {pages_to_scrape} pages")

    all_results: list[dict] = []

    for page_num in range(1, pages_to_scrape + 1):
        if page_num == 1:
            url = base_url
        else:
            offset = (page_num - 1) * items_per_page
            url = f"{base_url}&o={offset}"

        print(f"\n[pcwrap] Scraping page {page_num}/{pages_to_scrape}...")
        print(f"[pcwrap] URL: {url}")

        if page_num > 1:
            delay = random.uniform(4.0, 9.0)
            print(f"[pcwrap] Waiting {delay:.1f}s before next page...")
            time.sleep(delay)

        results = asyncio.run(scrape_pcwrap(url))
        print(f"[pcwrap] Found {len(results)} items on page {page_num}")
        all_results.extend(results)

    print(f"\n[pcwrap] Total items scraped: {len(all_results)}")
    return all_results


if __name__ == "__main__":
    results = run_pcwrap_scraper(max_pages=2)

    import polars as pl

    df = pl.DataFrame(results)
    df.write_csv("pcwrap_scraped.csv")
    print(f"Saved {len(df)} items to pcwrap_scraped.csv")
