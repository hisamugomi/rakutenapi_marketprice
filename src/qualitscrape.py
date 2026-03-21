"""
Scraper for https://www.yrl-qualit.com — Qualit used PC retailer.
Scrapes laptop listings from the category page, paginated via /page{N}/.

Extracted fields per listing:
  itemCode, itemName, itemUrl, itemPrice, shopName, source, search_query,
  is_active, scraped_at, brand, model, os, cpu, cpu_gen, memory, ssd, hdd,
  display_size, condition
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx
from bs4 import BeautifulSoup, Comment

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

BASE_URL = "https://www.yrl-qualit.com"
# ct01 = ノートパソコン (laptops)
CATEGORY_URL = f"{BASE_URL}/shopbrand/ct01/page{{page}}/recommend/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _parse_condition(title: str) -> str | None:
    """Extract condition code from title like [A:美品], [B:良品], [C:並品], [訳あり品], [バリュー品]."""
    m = re.search(r"\[([ABC]):([^\]]+)\]", title)
    if m:
        return m.group(1)
    if "訳あり" in title:
        return "Junk"
    if "バリュー" in title:
        return "Value"
    return None


def _parse_comment_specs(comment_text: str) -> dict:
    """Parse the structured spec data hidden in HTML comments.

    The comment block contains lines like:
        メーカLenovo
        CPUCore i5-2.1GHz(13420H)
        CPU世代第13世代
        メモリ16GB DDR4
        ストレージ256GB SSD
    """
    specs: dict = {}

    # Brand / maker
    m = re.search(r"メーカ\s*(.+?)(?:\n|$)", comment_text)
    if m:
        specs["brand"] = m.group(1).strip()

    # Series / model
    m = re.search(r"シリーズ名\s*(.+?)(?:\n|$)", comment_text)
    if m:
        specs["series"] = m.group(1).strip()

    # Model number
    m = re.search(r"型名\s*(.+?)(?:\n|$)", comment_text)
    if m:
        specs["model_number"] = m.group(1).strip()

    # OS
    m = re.search(r"OS\s*(Windows\S*\s*\S*|macOS\S*)", comment_text)
    if m:
        specs["os"] = m.group(1).strip()

    # CPU
    m = re.search(r"CPU\s*(Core\s+i\d[^\n]+|Ryzen[^\n]+|Celeron[^\n]+|Pentium[^\n]+)", comment_text)
    if m:
        specs["cpu"] = m.group(1).strip()

    # CPU generation
    m = re.search(r"CPU世代\s*第(\d+)世代", comment_text)
    if m:
        specs["cpu_gen"] = f"第{m.group(1)}世代"

    # Memory
    m = re.search(r"メモリ\s*(\d+)\s*GB", comment_text)
    if m:
        specs["memory"] = f"{m.group(1)}GB"

    # Storage
    m = re.search(r"ストレージ\s*(\d+)\s*(?:GB|TB)\s*(SSD|HDD|NVMe|M\.2|PCIe)?", comment_text)
    if m:
        size_str = m.group(0).strip()
        size_m = re.search(r"(\d+)\s*(GB|TB)", size_str)
        if size_m:
            size_val = size_m.group(1)
            size_unit = size_m.group(2)
            storage_str = f"{size_val}{size_unit}"
            # Determine SSD vs HDD
            if "HDD" in size_str and "SSD" not in size_str:
                specs["hdd"] = storage_str
            else:
                specs["ssd"] = storage_str

    # Product ID
    m = re.search(r"商品番号\s*(\S+)", comment_text)
    if m:
        specs["product_id"] = m.group(1).strip()

    return specs


def _extract_from_title(title: str) -> dict:
    """Fallback: extract specs from the slash-separated title.

    Title format:
      {Brand} {Series}(OS) 中古 {CPU}/{memory}/{storage}/{size}/extras [condition] ...
    After '中古', fields are '/'-separated.
    """
    specs: dict = {}

    # OS in parentheses before 中古: "(Win11x64)"
    if "(" in title and ")" in title:
        paren = title[title.index("(") + 1 : title.index(")")]
        if "Win" in paren or "mac" in paren.lower():
            specs["os"] = paren

    # Split on '中古' to get the spec portion, then split on '/'
    if "中古" not in title:
        return specs

    spec_part = title.split("中古", 1)[1].split("[")[0]  # strip condition suffix
    segments = [s.strip() for s in spec_part.split("/") if s.strip()]

    for seg in segments:
        # CPU: first segment (e.g. "Core i5-2.1GHz(13420H)")
        if "Core" in seg or "Ryzen" in seg or "Celeron" in seg:
            specs["cpu"] = seg.strip()

        # Memory: "16GB" or "メモリ16GB" or "メモリ32GB"
        elif "GB" in seg and ("メモリ" in seg or seg.replace("GB", "").isdigit()):
            specs["memory"] = seg.replace("メモリ", "").strip()

        # Storage: "SSD256GB" or "HDD500GB"
        elif "SSD" in seg or "HDD" in seg or "NVMe" in seg:
            storage_str = seg.replace("SSD", "").replace("NVMe", "").replace("HDD", "").strip()
            if "HDD" in seg:
                specs["hdd"] = storage_str
            else:
                specs["ssd"] = storage_str

        # Screen size: "15.6インチ" or "フルHD15.6" or bare "14" or "13.3"
        else:
            cleaned = seg.replace("フルHD", "").replace("WUXGA", "").replace("HD", "").replace("インチ", "").strip()
            try:
                size = float(cleaned)
                if 10 <= size <= 20:
                    specs["display_size"] = size
            except ValueError:
                pass

    return specs


def parse_qualit_listings(html: str) -> list[dict]:
    """Parse a Qualit category page and return a list of product dicts.

    Args:
        html: Raw HTML of a yrl-qualit.com category page.

    Returns:
        List of dicts matching the project's standard scraper output format.
    """
    soup = BeautifulSoup(html, "html.parser")
    scraped_at = datetime.now(JST).isoformat()
    results: list[dict] = []

    for li in soup.select("ul.innerList li"):
        try:
            name_tag = li.select_one("p.name a")
            if not name_tag:
                continue

            title = name_tag.get_text(strip=True)
            href = name_tag.get("href", "")

            # Extract product ID from URL: /shopdetail/000000014958/
            m = re.search(r"/shopdetail/(\d+)/", href)
            source_id = m.group(1) if m else href
            item_url = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Price
            price_em = li.select_one("em.price")
            item_price: int | None = None
            if price_em:
                price_text = price_em.get_text().replace(",", "").strip()
                price_match = re.search(r"\d+", price_text)
                item_price = int(price_match.group()) if price_match else None

            # Parse specs from HTML comments (the detailed spec block)
            comment_specs: dict = {}
            for comment in li.find_all(string=lambda text: isinstance(text, Comment)):
                comment_text = str(comment)
                if "商品番号" in comment_text or "メーカ" in comment_text:
                    comment_specs = _parse_comment_specs(comment_text)
                    break

            # Fallback: parse from title
            title_specs = _extract_from_title(title)

            # Merge: comment specs take priority, title specs fill gaps
            cpu = comment_specs.get("cpu") or title_specs.get("cpu")
            memory = comment_specs.get("memory") or title_specs.get("memory")
            ssd = comment_specs.get("ssd") or title_specs.get("ssd")
            hdd = comment_specs.get("hdd") or title_specs.get("hdd")
            os_val = comment_specs.get("os") or title_specs.get("os")
            display_size = title_specs.get("display_size")
            brand = comment_specs.get("brand")
            series = comment_specs.get("series", "")
            model_number = comment_specs.get("model_number", "")
            model = f"{series} {model_number}".strip() or None
            cpu_gen = comment_specs.get("cpu_gen")
            condition = _parse_condition(title)
            product_id = comment_specs.get("product_id", source_id)

            results.append({
                "itemCode": product_id,
                "itemName": title,
                "itemPrice": item_price,
                "itemUrl": item_url,
                "shopName": "Qualit",
                "source": "qualit",
                "search_query": "qualit_notebooks",
                "is_active": True,
                "scraped_at": scraped_at,
                "brand": brand,
                "model": model,
                "os": os_val,
                "cpu": cpu,
                "cpu_gen": cpu_gen,
                "memory": memory,
                "ssd": ssd,
                "hdd": hdd,
                "display_size": display_size,
                "condition": condition,
            })
        except Exception as e:
            logger.warning(f"[qualit] Error parsing item: {e}")
            continue

    return results


async def _fetch_page(client: httpx.AsyncClient, page: int) -> str:
    """Fetch a single category page."""
    url = CATEGORY_URL.format(page=page)
    resp = await client.get(url, headers=HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


async def _scrape_all_pages(max_pages: int | None = None) -> list[dict]:
    """Scrape all pages of Qualit laptop listings.

    Args:
        max_pages: Maximum number of pages to scrape (None = auto-detect).

    Returns:
        Combined list of item dicts from all pages.
    """
    all_results: list[dict] = []

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch first page to check for content
        page_num = 1
        while True:
            if max_pages and page_num > max_pages:
                break

            logger.info(f"[qualit] Fetching page {page_num}...")
            print(f"[qualit] Fetching page {page_num}...")

            try:
                html = await _fetch_page(client, page_num)
            except httpx.HTTPStatusError as e:
                logger.warning(f"[qualit] HTTP error on page {page_num}: {e}")
                break

            items = parse_qualit_listings(html)
            if not items:
                logger.info(f"[qualit] No items on page {page_num}, stopping.")
                print(f"[qualit] No items on page {page_num}, stopping.")
                break

            all_results.extend(items)
            print(f"[qualit] Page {page_num}: {len(items)} items")
            page_num += 1

            # Polite delay between pages
            await asyncio.sleep(2.0)

    return all_results


def run_qualit_scraper(max_pages: int | None = None) -> list[dict]:
    """Sync entry point — scrapes Qualit laptop listings.

    Args:
        max_pages: Maximum number of pages to scrape (None = all).

    Returns:
        List of item dicts.
    """
    results = asyncio.run(_scrape_all_pages(max_pages))
    print(f"[qualit] Total scraped: {len(results)}")
    return results


# ── Sample HTML (used in tests) ───────────────────────────────────────────────
# Minimal representative HTML matching the yrl-qualit.com listing structure.
SAMPLE_HTML = """
<div class="section" id="r_categoryList">
    <ul class="innerList">
        <li class="">
            <div class="innerBox">
                <div class="imgWrap">
                    <a href="https://www.yrl-qualit.com/shopdetail/000000014958/ct01/page1/recommend/"><img alt="Lenovo ThinkPad E16 Gen 1" src="https://example.com/img1.jpg"></a>
                </div>
                <div class="detail">
                    <p class="name"><a href="https://www.yrl-qualit.com/shopdetail/000000014958/ct01/page1/recommend/">Lenovo ThinkPad E16 Gen 1(Win11x64)  中古 Core i5-2.1GHz(13420H)/16GB/SSD256GB/16/Wi-Fi6/テンキー/Webカメラ [C:並品] 2025年頃購入 [期間限定セール]</a></p>
                    <p class="quantity"><span class="M_item-stock-smallstock M_category-smallstock">残りあと71個</span></p>
                    <p class="price">販売価格（消費税込）<br><em class="price">95,700</em>円</p>
                    <!--
                    <div class="content">

商品番号5726342c
種別中古パソコン
分類A4ノート
メーカLenovo
シリーズ名ThinkPad E16 Gen 1
型名21JQS7Y600
OSWindows11 Pro 64bit
CPUCore i5-2.1GHz(13420H)
CPU世代第13世代
メモリ16GB DDR4
ストレージ256GB SSD</div>
                    -->
                </div>
            </div>
        </li>
        <li class="">
            <div class="innerBox">
                <div class="imgWrap">
                    <a href="https://www.yrl-qualit.com/shopdetail/000000014951/ct01/page1/recommend/"><img alt="HP ProBook 450 G8" src="https://example.com/img2.jpg"></a>
                </div>
                <div class="detail">
                    <p class="name"><a href="https://www.yrl-qualit.com/shopdetail/000000014951/ct01/page1/recommend/">HP ProBook 450 G8(Win11x64)  中古 Core i7-2.8GHz(1165G7)/メモリ32GB/SSD256GB/フルHD15.6インチ/Webカメラ [C:並品]  [期間限定セール]</a></p>
                    <p class="quantity"><span class="M_item-stock-smallstock M_category-smallstock">残りあと1個</span></p>
                    <p class="price">販売価格（消費税込）<br><em class="price">57,200</em>円</p>
                    <!--
                    <div class="content">

商品番号5726635c
種別中古パソコン
分類A4ノート
メーカHP
シリーズ名ProBook 450 G8
型名55Q12AV-AAAQ
OSWindows11 Pro 64bit
CPUCore i7-2.8GHz (1165G7)
CPU世代第11世代
メモリ32GB DDR4-3200
ストレージ256GB SSD NVMe</div>
                    -->
                </div>
            </div>
        </li>
        <li class="lastChild">
            <div class="innerBox">
                <div class="imgWrap">
                    <a href="https://www.yrl-qualit.com/shopdetail/000000014946/ct01/page1/recommend/"><img alt="HP EliteBook 850 G6" src="https://example.com/img3.jpg"></a>
                </div>
                <div class="detail">
                    <p class="name"><a href="https://www.yrl-qualit.com/shopdetail/000000014946/ct01/page1/recommend/">HP EliteBook 850 G6(Win10x64)  中古 Core i5-1.6GHz(8265U)/メモリ16GB/SSD512GB/フルHD15.6/Wi-Fi6/Webカメラ [訳あり品] 2020年頃購入</a></p>
                    <p class="quantity"><span class="M_item-stock-smallstock M_category-smallstock">残りあと7個</span></p>
                    <p class="price">販売価格（消費税込）<br><em class="price">31,900</em>円</p>
                    <!--
                    <div class="content">

商品番号8643080w
種別中古パソコン
分類A4ノート
メーカHP
シリーズ名EliteBook 850 G6
型名8LA84PA-AAAB
OSWindows10 Pro 64bit
CPUCore i5-1.6GHz (8265U)
CPU世代第8世代
メモリ16GB DDR4
ストレージ512GB SSD</div>
                    -->
                </div>
            </div>
        </li>
    </ul>
</div>
"""


if __name__ == "__main__":
    import polars as pl

    results = run_qualit_scraper(max_pages=3)
    if results:
        df = pl.from_dicts(results)
        print(df)
        df.write_csv("data/qualit_scraped.csv")
        print(f"Saved {len(df)} items to data/qualit_scraped.csv")
