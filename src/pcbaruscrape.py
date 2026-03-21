"""
Scraper for https://www.smaphodock24.jp/used/ — PCバル used PC retailer.
Scrapes used notebook listings from the category page (sc1=25), paginated via pg_now=N.
Fetches detail pages for full specs (CPU, storage, display, SKU).

Extracted fields per listing:
  itemCode, itemName, itemUrl, itemPrice, shopName, source, search_query,
  is_active, scraped_at, brand, model, os, cpu, memory, ssd, hdd,
  display_size, condition
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

BASE_URL = "https://www.smaphodock24.jp/used"
# sc1=25 = 中古ノートパソコン (used notebooks)
LISTINGS_URL = f"{BASE_URL}/item_list.php?sc1=25&ka=1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_condition(condition_text: str) -> str | None:
    """Map Japanese condition text to a simplified grade."""
    mapping = {
        "新品または未開封品": "S",
        "新品同様・展示使用のみ": "A",
        "使用感少なくきれいな状態": "A",
        "使用感あるが良い状態": "B",
        "やや汚れ・劣化あり": "C",
        "汚れ・劣化あり": "D",
        "一部機能に問題あり": "Junk",
    }
    return mapping.get(condition_text.strip(), condition_text.strip() or None)


def _extract_screen_size(title: str) -> float | None:
    """Extract screen size in inches from the product title."""
    m = re.search(r"(\d{2}(?:\.\d+)?)\s*(?:インチ|inch)", title, re.IGNORECASE)
    if m:
        size = float(m.group(1))
        if 10 <= size <= 20:
            return size
    # Try bare number pattern like "13.3" before a space or end
    m = re.search(r"\b(\d{2}\.\d)\b", title)
    if m:
        size = float(m.group(1))
        if 10 <= size <= 20:
            return size
    return None


def parse_pcbaru_listings(html: str, search_query: str = "pcbaru_notebooks") -> list[dict]:
    """Parse a PCバル listing page and return a list of product dicts.

    Args:
        html: Raw HTML of a smaphodock24.jp/used listing page.
        search_query: Label stored on each row.

    Returns:
        List of dicts matching the project's standard scraper output format.
    """
    soup = BeautifulSoup(html, "html.parser")
    scraped_at = datetime.now(JST).isoformat()
    results: list[dict] = []

    for box in soup.select("div.item_box"):
        try:
            anchor = box.find("a", href=True)
            if not anchor:
                continue

            href = anchor.get("href", "")
            # Extract ID from detail.php?id=17821&page=1&ka=1
            m = re.search(r"detail\.php\?id=(\d+)", href)
            if not m:
                continue
            item_id = m.group(1)
            item_url = f"{BASE_URL}/{href}" if not href.startswith("http") else href

            # Brand from span.mfr_tx
            brand_tag = anchor.select_one("span.mfr_tx")
            brand = brand_tag.get_text(strip=True) if brand_tag else None

            # Product name from div.item_ti
            name_tag = anchor.select_one("div.item_ti")
            item_name = name_tag.get_text(strip=True) if name_tag else ""

            # Specs from div.item_spec1 elements — split on " : " separator
            spec_divs = anchor.select("div.item_spec1")
            specs: dict[str, str] = {}
            os_val = None
            for spec_div in spec_divs:
                text = spec_div.get_text(strip=True)
                if " : " in text:
                    label, _, value = text.partition(" : ")
                    specs[label.strip()] = value.strip()
                elif any(kw in text for kw in ["Windows", "macOS", "Chrome OS", "Linux"]):
                    os_val = text
            cpu_val = specs.get("CPU")
            memory_val = specs.get("メモリ")

            # Condition from li.evaluation_rating
            condition_tag = box.select_one("li.evaluation_rating")
            condition_text = condition_tag.get_text(strip=True) if condition_tag else ""
            condition = _parse_condition(condition_text)

            # Price from div.price_tx strong
            price_tag = box.select_one("div.price_tx strong")
            item_price: int | None = None
            if price_tag:
                price_text = price_tag.get_text().replace(",", "").replace("円", "").strip()
                price_match = re.search(r"\d+", price_text)
                item_price = int(price_match.group()) if price_match else None

            # Shop/store from div.zaiko_shop a
            shop_tag = box.select_one("div.zaiko_shop a")
            shop_name = f"PCバル {shop_tag.get_text(strip=True)}" if shop_tag else "PCバル"

            # Screen size from title
            display_size = _extract_screen_size(item_name)

            results.append(
                {
                    "itemCode": item_id,
                    "itemName": item_name,
                    "itemPrice": item_price,
                    "itemUrl": item_url,
                    "shopName": shop_name,
                    "source": "pcbaru",
                    "search_query": search_query,
                    "is_active": True,
                    "scraped_at": scraped_at,
                    "brand": brand,
                    "os": os_val,
                    "cpu": cpu_val,
                    "memory": memory_val,
                    "display_size": display_size,
                    "condition": condition,
                }
            )
        except Exception as e:
            logger.warning(f"[pcbaru] Error parsing listing card: {e}")
            continue

    return results


def parse_pcbaru_detail(html: str) -> dict:
    """Parse a PCバル detail page and return specs dict.

    Args:
        html: Raw HTML of a smaphodock24.jp/used/detail.php page.

    Returns:
        Dict with keys: sku, model_number, cpu, memory, storage, storage_type,
        os, display_size, display_resolution, condition, and extras.
    """
    soup = BeautifulSoup(html, "html.parser")
    specs: dict = {}

    # SKU from JSON-LD
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "Product":
                specs["sku"] = data.get("sku", "")
                break
        except (json.JSONDecodeError, TypeError):
            continue

    # Specs from table#item_tbl_lay
    for table in soup.select("table#item_tbl_lay"):
        for row in table.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)
            if value in ("－", "-", ""):
                continue

            if label == "メーカー":
                specs["brand"] = value
            elif label == "型番":
                specs["model_number"] = value
            elif label == "CPU":
                specs["cpu"] = value
            elif label == "メモリ":
                specs["memory"] = value
            elif label == "ストレージ":
                specs["storage_raw"] = value
                # Parse "SSD 256GB" or "HDD 500GB"
                if "HDD" in value:
                    size_m = re.search(r"(\d+)\s*(?:GB|TB)", value)
                    if size_m:
                        specs["hdd"] = (
                            f"{size_m.group(1)}{size_m.group(0).split(size_m.group(1))[-1].strip()}"
                        )
                else:
                    size_m = re.search(r"(\d+)\s*(?:GB|TB)", value)
                    if size_m:
                        specs["ssd"] = (
                            f"{size_m.group(1)}{size_m.group(0).split(size_m.group(1))[-1].strip()}"
                        )
            elif label == "OS":
                specs["os"] = value
            elif label == "ディスプレイ":
                try:
                    specs["display_size"] = float(value.replace("インチ", "").strip())
                except ValueError:
                    pass
            elif label == "ディスプレイ解像度":
                specs["display_resolution"] = value

    # Condition from div.evaluation_rating
    cond_tag = soup.select_one("div.evaluation_rating")
    if cond_tag:
        specs["condition"] = _parse_condition(cond_tag.get_text(strip=True))

    return specs


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a single page."""
    resp = await client.get(url, headers=HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


async def _scrape_all_pages(
    max_pages: int | None = None,
    fetch_details: bool = False,
) -> list[dict]:
    """Scrape all pages of PCバル used notebook listings.

    Args:
        max_pages: Maximum number of pages to scrape (None = auto-detect).
        fetch_details: If True, also fetch each detail page for full specs + SKU.

    Returns:
        Combined list of item dicts from all pages.
    """
    all_results: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        page_num = 1
        while True:
            if max_pages and page_num > max_pages:
                break

            url = LISTINGS_URL if page_num == 1 else f"{LISTINGS_URL}&pg_now={page_num}"
            logger.info(f"[pcbaru] Fetching page {page_num}...")
            print(f"[pcbaru] Fetching page {page_num}: {url}")

            try:
                html = await _fetch_page(client, url)
            except httpx.HTTPStatusError as e:
                logger.warning(f"[pcbaru] HTTP error on page {page_num}: {e}")
                break

            items = parse_pcbaru_listings(html)
            if not items:
                logger.info(f"[pcbaru] No items on page {page_num}, stopping.")
                print(f"[pcbaru] No items on page {page_num}, stopping.")
                break

            all_results.extend(items)
            print(f"[pcbaru] Page {page_num}: {len(items)} items")
            page_num += 1

            # Polite delay between pages
            await asyncio.sleep(2.0)

        # Optionally enrich with detail page data
        if fetch_details and all_results:
            print(f"[pcbaru] Fetching {len(all_results)} detail pages...")
            for i, item in enumerate(all_results):
                detail_url = item["itemUrl"]
                try:
                    detail_html = await _fetch_page(client, detail_url)
                    detail_specs = parse_pcbaru_detail(detail_html)

                    # Enrich with detail data (detail takes priority)
                    if detail_specs.get("sku"):
                        item["itemCode"] = detail_specs["sku"]
                    if detail_specs.get("cpu"):
                        item["cpu"] = detail_specs["cpu"]
                    if detail_specs.get("memory"):
                        item["memory"] = detail_specs["memory"]
                    if detail_specs.get("ssd"):
                        item["ssd"] = detail_specs["ssd"]
                    if detail_specs.get("hdd"):
                        item["hdd"] = detail_specs["hdd"]
                    if detail_specs.get("os"):
                        item["os"] = detail_specs["os"]
                    if detail_specs.get("display_size"):
                        item["display_size"] = detail_specs["display_size"]
                    if detail_specs.get("model_number"):
                        item["model"] = detail_specs["model_number"]
                    if detail_specs.get("condition"):
                        item["condition"] = detail_specs["condition"]

                    if (i + 1) % 20 == 0:
                        print(f"[pcbaru] Detail pages: {i + 1}/{len(all_results)}")
                    await asyncio.sleep(1.5)
                except Exception as e:
                    logger.warning(f"[pcbaru] Error fetching detail {detail_url}: {e}")
                    continue

    return all_results


def run_pcbaru_scraper(
    max_pages: int | None = None,
    fetch_details: bool = False,
) -> list[dict]:
    """Sync entry point — scrapes PCバル used notebook listings.

    Args:
        max_pages: Maximum number of pages to scrape (None = all).
        fetch_details: If True, also fetch detail pages for full specs + SKU.

    Returns:
        List of item dicts.
    """
    results = asyncio.run(_scrape_all_pages(max_pages, fetch_details))
    print(f"[pcbaru] Total scraped: {len(results)}")
    return results


# ── Sample HTML (used in tests) ───────────────────────────────────────────────
# Minimal representative HTML matching the smaphodock24.jp/used listing structure.
SAMPLE_HTML = """\
<div class="item_box">
    <a href="detail.php?id=17821&page=1&ka=1">
        <figure>
            <img src="./lib/resize_image.php?size=250&path=.././upload/item/17809_1.jpg" alt="">
        </figure>
        <div class="item_name_group">
            <span class="mfr_tx">Lenovo</span>
            <div class="item_ti">Lenovo ThinkPad L13 13.3 Intel Core i5-10210U 8GB</div>
        </div>
        <div class="item_spec1">性能もサイズも軽さもお値段も、全てちょうどいいレノボの13.3インチノート!</div>
        <div class="item_spec1">Windows11 Pro 64bit</div>
        <div class="item_spec1">CPU : Intel Core i5-10210U</div>
        <div class="item_spec1">メモリ : 8GB</div>
        <ul class="evaluation_box">
            <li class="evaluation_rating">使用感あるが良い状態</li>
        </ul>
        <div class="price_tx">
            <strong>38,500円</strong><span class="s_tx">（税込）<strong class="m_tx">送料無料</strong></span>
        </div>
    </a>
    <div class="zaiko_shop"><a href="shop_detail.php?id=37">福岡姪浜店</a></div>
</div>

<div class="item_box">
    <a href="detail.php?id=15501&page=1&ka=1">
        <figure>
            <img src="./lib/resize_image.php?size=250&path=.././upload/item/15468_1.jpg" alt="">
        </figure>
        <div class="item_name_group">
            <span class="mfr_tx">DELL</span>
            <div class="item_ti">DELL Latitude 3510 15.6 Intel Core i5-10210U 8GB</div>
        </div>
        <div class="item_spec1">DELL15.6インチスタンダードノート。10世代i5CPU、Windows11搭載！</div>
        <div class="item_spec1">Windows 11 Pro (64bit)</div>
        <div class="item_spec1">CPU : Intel Core i5-10210U</div>
        <div class="item_spec1">メモリ : 8GB</div>
        <ul class="evaluation_box">
            <li class="evaluation_rating">使用感あるが良い状態</li>
        </ul>
        <div class="price_tx">
            <strong>38,500円</strong><span class="s_tx">（税込）<strong class="m_tx">送料無料</strong></span>
        </div>
    </a>
    <div class="zaiko_shop"><a href="shop_detail.php?id=28">札幌店</a></div>
</div>

<div class="item_box">
    <a href="detail.php?id=14503&page=1&ka=1">
        <figure>
            <img src="./lib/resize_image.php?size=250&path=.././upload/item/14483_1.jpg" alt="">
        </figure>
        <div class="item_name_group">
            <span class="mfr_tx">Panasonic</span>
            <div class="item_ti">Panasonic Lets note SV8 12.1inch Intel Core i5-8350U 8GB</div>
        </div>
        <div class="item_spec1">シゴデキビジネスマン御用達！人気のLet's note、Windows11搭載！</div>
        <div class="item_spec1">Windows 11 Pro 64bit</div>
        <div class="item_spec1">CPU : Intel Core i5-8350U</div>
        <div class="item_spec1">メモリ : 8GB</div>
        <ul class="evaluation_box">
            <li class="evaluation_rating">使用感少なくきれいな状態</li>
        </ul>
        <div class="price_tx">
            <strong>42,900円</strong><span class="s_tx">（税込）<strong class="m_tx">送料無料</strong></span>
        </div>
    </a>
    <div class="zaiko_shop"><a href="shop_detail.php?id=22">町田店</a></div>
</div>
"""

SAMPLE_DETAIL_HTML = """\
<html>
<head>
<script type="application/ld+json">
{
    "@context": "https://schema.org",
    "@type": "Product",
    "name": "Lenovo ThinkPad L13 13.3 Intel Core i5-10210U 8GB [2060601A0920]",
    "sku": "2060601A0920",
    "brand": {"@type": "Brand", "name": "Lenovo"},
    "offers": {
        "@type": "Offer",
        "price": "38500",
        "priceCurrency": "JPY",
        "availability": "https://schema.org/InStock"
    }
}
</script>
</head>
<body>
<h2 class="pageti" itemprop="name">Lenovo ThinkPad L13 13.3 Intel Core i5-10210U 8GB [2060601A0920]</h2>
<div class="evaluation_wrap">
    <h4 class="title05">商品の状態</h4>
    <div class="evaluation_rating">使用感あるが良い状態</div>
</div>
<div id="spec_list_area" class="ly_card_2column">
    <div id="item_tbl_wrapper">
        <table id="item_tbl_lay" class="sheet_basic tx_left s_pd">
            <tbody>
                <tr><th>メーカー</th><td class="lay1"><span>Lenovo</span></td></tr>
                <tr><th>型番</th><td class="lay2"><span>TP00114A</span></td></tr>
                <tr><th>CPU</th><td class="lay1"><span>Intel Core i5-10210U</span></td></tr>
                <tr><th>メモリ</th><td class="lay2"><span>8GB</span></td></tr>
                <tr><th>ストレージ</th><td class="lay1"><span>SSD 256GB</span></td></tr>
                <tr><th>グラフィック</th><td class="lay2"><span>Intel UHD Graphics</span></td></tr>
                <tr><th>光学ドライブ</th><td class="lay1"><span>－</span></td></tr>
                <tr><th>ネットワーク</th><td class="lay2"><span>無線LAN：IEEE802.11a/b/g/n/ac/ax(Wi-Fi 6)準拠</span></td></tr>
            </tbody>
        </table>
    </div>
    <div id="item_tbl_wrapper">
        <table id="item_tbl_lay" class="sheet_basic tx_left s_pd">
            <tbody>
                <tr><th>OS</th><td class="lay1"><span>Windows11 Pro 64bit</span></td></tr>
                <tr><th>Office</th><td class="lay2">－</td></tr>
                <tr><th>ディスプレイ</th><td class="lay1"><span>13.3</span></td></tr>
                <tr><th>ディスプレイ解像度</th><td class="lay2"><span>1920×1080</span></td></tr>
                <tr><th>付属品</th><td class="lay1"><span>ACアダプター</span></td></tr>
                <tr><th>備考1</th><td class="lay2"><span>Webカメラ、Bluetooth</span></td></tr>
                <tr><th>備考2</th><td class="lay1"><span>USB3.0×2、USB Type-C×2</span></td></tr>
            </tbody>
        </table>
    </div>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    import polars as pl

    results = run_pcbaru_scraper(max_pages=3, fetch_details=True)
    if results:
        df = pl.from_dicts(results)
        print(df)
        df.write_csv("data/pcbaru_scraped.csv")
        print(f"Saved {len(df)} items to data/pcbaru_scraped.csv")
