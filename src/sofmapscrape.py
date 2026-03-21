"""
This is a scraping service to scrape used computers off of sofmap.com
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

SAMPLE_HTML = """
<div class="mainbox">
<a class="itemimg" href="https://www.sofmap.com/product_detail.aspx?sku=414477263">
<img alt="" class="ic usedrank" src="https://www.sofmap.com/images/static/img/ic_usedrank_B.svg"/>
<img alt="" decoding="async" loading="lazy" src="https://image.sofmap.com/images/product/large/2133067933344_1.jpg"/>
</a>
<div class="icon-box"><i class="ic item-type used">中古商品</i></div>
<span class="brand">MSI(エムエスアイ)</span>
<span class="brand brand_type_list" style="display:none;">MSI(エムエスアイ)</span>
<a class="product_name" href="https://www.sofmap.com/product_detail.aspx?sku=414477263">〔中古品〕 Prestige 16 Prestige-16-AI-Studio-B1VGG-1903JP ステラグレイ ［Core-Ultra-9-185H／32GB／SSD1TB／16インチ／Windows11 Pro］</a>
<a class="product_name product_name_type_list" href="https://www.sofmap.com/product_detail.aspx?sku=414477263" style="display:none;">〔中古品〕 Prestige 16 Prestige-16-AI-Studio-B1VGG-1903JP ステラグレイ ［Core-Ultra-9-185H／32GB／SSD1TB／16インチ／Windows11 Pro］</a>
<div class="item_label"></div>
<span class="price"><strong>¥259,980<i>(税込)</i></strong></span>
<span class="point">12,999ポイントサービス </span>
<dl class="used_link shop"><dt>取扱店舗</dt><dd><a href="https://www.sofmap.com/tenpo/?id=shops&amp;sid=ike_reuse"><img alt="" src="/images/static/img/ic_used_tempo.svg"/>池袋店</a></dd></dl>
</div>

<div class="mainbox">
<a class="itemimg" href="/search_result.aspx?product_type=USED&amp;new_jan=4526541197468&amp;gid=001010110&amp;used_rank=0009+0003+0002+0001+0006+0004">
<img alt="" decoding="async" loading="lazy" src="https://image.sofmap.com/images/product/large/2133072790222_1.jpg"/>
</a>
<div class="icon-box"><i class="ic item-type used">中古商品</i></div>
<span class="brand">MSI(エムエスアイ)</span>
<span class="brand brand_type_list" style="display:none;">MSI(エムエスアイ)</span>
<a class="product_name" href="/search_result.aspx?product_type=USED&amp;new_jan=4526541197468&amp;gid=001010110&amp;used_rank=0009+0003+0002+0001+0006+0004">〔展示品〕 Cyborg 15 A12V Cyborg-15-A12UC-3050JP ブラック&amp;スケルトン ［Core-i5-12450H (2GHz)／16GB／SSD512GB／GeForce RTX 3050(4GB)／15.6インチワイド／Windows11 Home］</a>
<a class="product_name product_name_type_list" href="/search_result.aspx?product_type=USED&amp;new_jan=4526541197468&amp;gid=001010110&amp;used_rank=0009+0003+0002+0001+0006+0004" style="display:none;">〔展示品〕 Cyborg 15 A12V Cyborg-15-A12UC-3050JP ブラック&amp;スケルトン ［Core-i5-12450H (2GHz)／16GB／SSD512GB／GeForce RTX 3050(4GB)／15.6インチワイド／Windows11 Home］</a>
<div class="item_label"></div>
<span class="price"><strong>¥109,980<i>(税込)～</i></strong></span>
<div class="used_box txt"><a href="/search_result.aspx?product_type=USED&amp;new_jan=4526541197468">中古商品が計4点あります</a></div>
<span class="point">5,499ポイントサービス </span>
</div>

<div class="mainbox">
<a class="itemimg" href="/search_result.aspx?product_type=USED&amp;new_jan=4573661272636&amp;gid=001010110&amp;used_rank=0009+0003+0002+0001+0006+0004">
<img alt="" decoding="async" loading="lazy" src="https://image.sofmap.com/images/product/large/2133071221710_1.jpg"/>
</a>
<div class="icon-box"><i class="ic item-type used">中古商品</i></div>
<span class="brand">DELL(デル)</span>
<span class="brand brand_type_list" style="display:none;">DELL(デル)</span>
<a class="product_name" href="/search_result.aspx?product_type=USED&amp;new_jan=4573661272636&amp;gid=001010110&amp;used_rank=0009+0003+0002+0001+0006+0004">〔展示品〕 Dell 15 DC15250 ND65-FWHBSC プラチナシルバー ［Core-i5-1334U (1.3GHz)／16GB／SSD512GB／15.6インチワイド／Windows11 Home］</a>
<a class="product_name product_name_type_list" href="/search_result.aspx?product_type=USED&amp;new_jan=4573661272636&amp;gid=001010110&amp;used_rank=0009+0003+0002+0001+0006+0004" style="display:none;">〔展示品〕 Dell 15 DC15250 ND65-FWHBSC プラチナシルバー ［Core-i5-1334U (1.3GHz)／16GB／SSD512GB／15.6インチワイド／Windows11 Home］</a>
<div class="item_label"></div>
<span class="price"><strong>¥114,980<i>(税込)～</i></strong></span>
<div class="used_box txt"><a href="/search_result.aspx?product_type=USED&amp;new_jan=4573661272636">中古商品が計6点あります</a></div>
<span class="point">5,749ポイントサービス </span>
</div>

<div class="mainbox">
<a class="itemimg" href="https://www.sofmap.com/product_detail.aspx?sku=414931730">
<img alt="" class="ic usedrank" src="https://www.sofmap.com/images/static/img/ic_usedrank_B.svg"/>
<img alt="" decoding="async" loading="lazy" src="https://image.sofmap.com/images/product/large/2133072805322_1.jpg"/>
</a>
<div class="icon-box"><i class="ic item-type used">中古商品</i></div>
<span class="brand">GIGABYTE(ギガバイト)</span>
<span class="brand brand_type_list" style="display:none;">GIGABYTE(ギガバイト)</span>
<a class="product_name" href="https://www.sofmap.com/product_detail.aspx?sku=414931730">〔展示品〕 GAMING A16 CVHI3JP864S</a>
<a class="product_name product_name_type_list" href="https://www.sofmap.com/product_detail.aspx?sku=414931730" style="display:none;">〔展示品〕 GAMING A16 CVHI3JP864S</a>
<div class="item_label"></div>
<span class="price"><strong>¥185,980<i>(税込)</i></strong></span>
<span class="point">9,299ポイントサービス </span>
<dl class="used_link shop"><dt>取扱店舗</dt><dd><a href="https://www.sofmap.com/tenpo/?id=shops&amp;sid=akiba_ekimae"><img alt="" src="/images/static/img/ic_used_tempo.svg"/>AKIBA 駅前館</a></dd></dl>
</div>
"""

async def findmaxlisting(url: str) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url=url, timeout=60000)
        raw_num = await page.locator("p.pg_number_set span").first.inner_text()
        # await page.pause()  # Remove this in production
        await browser.close()
        clean_num = int(raw_num.replace(",", "").strip())
        time.sleep(10)
        return clean_num

async def scrape_sofmap(url: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url=url, timeout=60000)

        item_containers = await page.locator("div.mainbox").all()
        results = []
        scraped_at = datetime.now(JST).isoformat()

        for item in item_containers:
            try:
                # Get product name
                namepart = await item.locator("a.product_name").first.inner_text()
                brand = await item.locator("span.brand").first.inner_text()
                name = f"{namepart} {brand}"

                # Get price
                price_raw = await item.locator("span.price strong").inner_text()
                price_text = price_raw.replace("¥", "").replace(",", "").replace("(税込)", "").replace("～", "").strip()

                # Get link and extract product ID
                link = await item.locator("a.product_name").first.get_attribute("href")

                # Handle two types of URLs
                if "sku=" in link:
                    product_id = link.split("sku=")[-1]
                elif "new_jan=" in link:
                    product_id = link.split("new_jan=")[-1].split("&")[0]
                else:
                    product_id = link  # fallback to full URL

                results.append({
                    "itemCode": product_id,
                    "itemName": name.strip(),
                    "itemPrice": int(price_text.split("(")[0].strip()),  # Handle "～" prices
                    "itemUrl": f"https://www.sofmap.com{link}" if not link.startswith("http") else link,
                    "scraped_at": scraped_at,
                    "search_query": "sofmap_notebooks",
                    "source": "sofmap",
                    "is_active": True,
                })
            except Exception as e:
                print(f"Error parsing item: {e}")
                continue  # skip malformed items

        await browser.close()
        return results

def run_sofmap_scraper(max_pages: int = None) -> list[dict]:
    """
    Sync entry point — runs all configured search URLs.

    Args:
        max_pages: Maximum number of pages to scrape (None = all pages)
    """
    all_results = []
    base_url = "https://www.sofmap.com/search_result.aspx"
    params = "?gid=001010110&used_rank=0009+0003+0002+0001+0006+0004&product_type=USED&order_by=&dispcnt=100"

    # First page to get total count
    first_page_url = base_url + params
    listingnum = asyncio.run(findmaxlisting(url=first_page_url))
    total_pages = (listingnum // 100) + (1 if listingnum % 100 > 0 else 0)

    # Determine how many pages to actually scrape
    pages_to_scrape = min(max_pages, total_pages) if max_pages else total_pages

    print(f"Total listings: {listingnum}")
    print(f"Total pages: {total_pages}")
    print(f"Scraping: {pages_to_scrape} pages")

    for page_num in range(1, pages_to_scrape + 1):
        # Add page number parameter
        if page_num == 1:
            url = first_page_url
        else:
            url = f"{base_url}{params}&pno={page_num}"

        print(f"\n[sofmap] Scraping page {page_num}/{pages_to_scrape}...")
        print(f"[sofmap] URL: {url}")

        if page_num > 1:
            print("[sofmap] Waiting 3s before next page...")
            time.sleep(3)  # Be respectful

        results = asyncio.run(scrape_sofmap(url))
        print(f"[sofmap] Found {len(results)} items on page {page_num}")

        all_results.extend(results)

    print(f"\n[sofmap] Total items scraped: {len(all_results)}")
    return all_results

if __name__ == "__main__":
    # Start with 5 pages for testing (500 items)
    results = run_sofmap_scraper(max_pages=5)

    # Optionally save to CSV
    import polars as pl
    df = pl.DataFrame(results)
    df.write_csv("data/sofmap_scraped.csv")
    print(f"Saved {len(df)} items to sofmap_scraped.csv")
