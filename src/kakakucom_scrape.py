"""
Kakaku.com used PC scraper.

Parses the .tblUsed table from kakaku.com/used/pc search results.
Each product occupies two rows — this parser only reads the first (data) row.

Extracted fields per listing:
  itemName, itemUrl, itemPrice, rank, os, cpu, storage, ram, screen,
  shopName, listedDate, source, search_query
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

JST = timezone(timedelta(hours=9))

BASE_URL = "https://kakaku.com"
SEARCH_URLS = {
    "L390":           f"{BASE_URL}/used/pc/ca=0020/?kwquery=L390",
    "L580":           f"{BASE_URL}/used/pc/ca=0020/?kwquery=L580",
    "L590":           f"{BASE_URL}/used/pc/ca=0020/?kwquery=L590",
    "Latitude 5300":  f"{BASE_URL}/used/pc/ca=0020/?kwquery=Latitude+5300",
    "Latitude 5400":  f"{BASE_URL}/used/pc/ca=0020/?kwquery=Latitude+5400",
    "Latitude 5490":  f"{BASE_URL}/used/pc/ca=0020/?kwquery=Latitude+5490",
    "Latitude 5500":  f"{BASE_URL}/used/pc/ca=0020/?kwquery=Latitude+5500",
    "Latitude 5590":  f"{BASE_URL}/used/pc/ca=0020/?kwquery=Latitude+5590",
}


def parse_kakaku_listings(html: str, search_query: str = "") -> list[dict]:
    """Parse a kakaku.com used-PC search results page.

    Args:
        html: Raw HTML of the search results page (or the .tblUsed table).
        search_query: The keyword used for the search, stored on each row.

    Returns:
        List of dicts, one per listing.
    """
    soup = BeautifulSoup(html, "html.parser")
    scraped_at = datetime.now(JST).isoformat()
    results = []

    # Each product's main data row contains a td.itemName cell
    for row in soup.find_all("tr"):
        name_cell = row.find("td", class_="itemName")
        if name_cell is None:
            continue

        # ── Product name and URL ──────────────────────────────────────────────
        strong = name_cell.find("strong")
        item_name = strong.get_text(strip=True) if strong else ""

        link = name_cell.find("a")
        href = link.get("href", "") if link else ""
        item_url = f"{BASE_URL}{href}" if href.startswith("/") else href

        # ── Price ─────────────────────────────────────────────────────────────
        price_cell = row.find("td", class_="priceData")
        price_text = price_cell.get_text(strip=True) if price_cell else ""
        try:
            item_price = int(price_text.replace("¥", "").replace(",", ""))
        except ValueError:
            item_price = None

        # ── colC cells: split rowspan=2 (shipping, rank) vs regular ──────────
        all_colc = row.find_all("td", class_="colC")
        rowspan_cells = [c for c in all_colc if c.get("rowspan") == "2"]
        regular_cells = [c for c in all_colc if c.get("rowspan") != "2"]

        # rank is the second rowspan=2 colC (first is shipping cost)
        rank = ""
        if len(rowspan_cells) >= 2:
            rank = rowspan_cells[1].get_text(strip=True)

        def _cell(idx: int) -> str:
            if idx < len(regular_cells):
                return regular_cells[idx].get_text(strip=True)
            return ""

        os_val     = _cell(0)
        cpu        = _cell(1)
        storage    = _cell(2)
        ram        = _cell(3)
        screen     = _cell(4)
        listed_date = _cell(5)

        # ── Shop name ─────────────────────────────────────────────────────────
        shop_cell = row.find("td", class_="colShop")
        shop_raw = shop_cell.get_text(strip=True) if shop_cell else ""
        # Drop "（店頭販売有）" suffix if present
        shop_name = shop_raw.split("（")[0].strip()

        if not item_name:
            continue

        results.append({
            "itemCode":     href.rstrip("/").split("/")[-1] if href else item_name,
            "itemName":     item_name,
            "itemUrl":      item_url,
            "itemPrice":    item_price,
            "rank":         rank,
            "os":           os_val,
            "cpu":          cpu,
            "storage":      storage,
            "ram":          ram,
            "screen":       screen,
            "shopName":     shop_name,
            "listedDate":   listed_date,
            "scraped_at":   scraped_at,
            "search_query": search_query,
            "source":       "kakaku",
            "is_active":    True,
        })

    return results


async def scrape_kakaku(search_key: str, url: str) -> list[dict]:
    """Fetch one kakaku.com search-results page and parse it."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url=url, timeout=60000)
        await page.wait_for_selector("table.tblUsed", timeout=15000)
        html = await page.content()
        await browser.close()

    return parse_kakaku_listings(html, search_query=search_key)


def run_kakaku_scraper() -> list[dict]:
    """Sync entry point — scrapes all SEARCH_URLS."""
    all_results = []
    for i, (key, url) in enumerate(SEARCH_URLS.items()):
        if i > 0:
            print("[kakaku] Waiting 5s before next keyword...")
            time.sleep(5)
        print(f"[kakaku] Scraping: {key}")
        try:
            results = asyncio.run(scrape_kakaku(key, url))
            print(f"[kakaku] {key}: {len(results)} items")
        except (PlaywrightTimeout, TimeoutError):
            print(f"No used items found for {key} or page failed to load.")
            results = []
        all_results.extend(results)
    return all_results


# ── Sample HTML (used in tests) ───────────────────────────────────────────────
# Copied from a real kakaku.com search results page for L390.
SAMPLE_HTML = """<table border="0" cellpadding="0" cellspacing="0" class="tblUsed">
<tbody><tr>
<th rowspan="2">製品画像</th>
<th rowspan="2">メーカー名・製品名</th>
<th rowspan="2">価格</th>
<th rowspan="2">送料</th>
<th rowspan="2">商品状態</th>
<th colspan="5">スペック</th>
<th rowspan="2">ショップ名/<br>店頭販売</th>
<th rowspan="2">登録日</th>
</tr>
<tr>
<th>OS</th><th>CPU</th><th>ストレージ(HDD/SSD)</th><th>メモリ</th><th>ディスプレイ</th>
</tr>

<tr onmouseover="" onmouseout="" class="trBorder" style="background-color: rgb(255, 255, 255);">
<td class="itemPhoto" rowspan="2"><a href="/used/pc/ca=0020/shop/12700/pUN20NSS0W1%2DA004L/"><img src="" alt="ThinkPad L390 20NSS0W100"></a></td>
<td rowspan="2" class="itemName">IBM<p><a href="/used/pc/ca=0020/shop/12700/pUN20NSS0W1%2DA004L/"><strong>ThinkPad L390 20NSS0W100</strong></a></p></td>
<td rowspan="2" class="priceData"><a href="/used/pc/ca=0020/shop/12700/pUN20NSS0W1%2DA004L/">¥19,400</a></td>
<td rowspan="2" class="colC">¥1,100～</td>
<td rowspan="2" class="colC"><p>Bランク</p></td>
<td class="colC">Windows 11 Pro</td>
<td class="colC">Core i3</td>
<td class="colC">128GB</td>
<td class="colC">8GB</td>
<td class="colC">13インチ</td>
<td class="colShop"><a href="/used/shop/12700/">Be-Stock</a></td>
<td class="colC">26/02/25</td></tr>
<tr class="trBorder"><td colspan="7" class="specData"><span>【ショップからのコメント】</span></td></tr>

<tr onmouseover="" onmouseout="" class="trBorder" style="background-color: rgb(255, 255, 255);">
<td class="itemPhoto" rowspan="2"><a href="/used/pc/ca=0020/shop/17008/p141/"><img src="" alt="lenovo ThinkPad L390 i5 8265U 8GB SSD256GB Win11Pro"></a></td>
<td rowspan="2" class="itemName">IBM<p><a href="/used/pc/ca=0020/shop/17008/p141/"><strong>lenovo ThinkPad L390 Core i5 8265U 8GB SSD256GB (Win11Pro)</strong></a></p></td>
<td rowspan="2" class="priceData"><a href="/used/pc/ca=0020/shop/17008/p141/">¥20,800</a></td>
<td rowspan="2" class="colC">¥2,000～</td>
<td rowspan="2" class="colC"><p>Bランク</p></td>
<td class="colC">Windows 11 Pro</td>
<td class="colC">Core i5</td>
<td class="colC">256GB</td>
<td class="colC">8GB</td>
<td class="colC">13インチ</td>
<td class="colShop"><a href="/used/shop/17008/">0799.jp</a><br>（店頭販売有）</td>
<td class="colC">26/02/25</td></tr>
<tr class="trBorder"><td colspan="7" class="specData"><span>【ショップからのコメント】</span>整備済み商品</td></tr>

<tr onmouseover="" onmouseout="" class="trBorder">
<td class="itemPhoto" rowspan="2"><a href="/used/pc/ca=0020/shop/12700/pUN20NSS41B%2DA002L/"><img src="" alt="ThinkPad L390 20NSS41B00"></a></td>
<td rowspan="2" class="itemName">IBM<p><a href="/used/pc/ca=0020/shop/12700/pUN20NSS41B%2DA002L/"><strong>ThinkPad L390 20NSS41B00</strong></a></p></td>
<td rowspan="2" class="priceData"><a href="/used/pc/ca=0020/shop/12700/pUN20NSS41B%2DA002L/">¥22,700</a></td>
<td rowspan="2" class="colC">¥1,100～</td>
<td rowspan="2" class="colC"><p>Bランク</p></td>
<td class="colC">無</td>
<td class="colC">Core i5</td>
<td class="colC">256GB</td>
<td class="colC">8GB</td>
<td class="colC">13インチ</td>
<td class="colShop"><a href="/used/shop/12700/">Be-Stock</a></td>
<td class="colC">26/02/24</td></tr>
<tr class="trBorder"><td colspan="7" class="specData"><span>【ショップからのコメント】</span></td></tr>

</tbody></table>"""


if __name__ == "__main__":
    results = run_kakaku_scraper()
    import polars as pl
    df = pl.DataFrame(results)
    df.write_csv("data/kakaku_scraped.csv")
    print(f"Saved {len(df)} items to kakaku_scraped.csv")
