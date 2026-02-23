"""
This is a scraping service to scrape used computers off of sofmap.com
"""


import asyncio
import time
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

    # "urlpage2": "https://www.sofmap.com/search_result.aspx?gid=001010110&used_rank=0009+0003+0002+0001+0006+0004&product_type=USED&order_by=&dispcnt=100",



async def findmaxlisting(url: str) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url=url, timeout=60000)

        raw_num = await page.locator("p.pg_number_set span").first.inner_text()
        await page.pause()
        await browser.close()
        clean_num = int(raw_num.replace(",", "").strip())
    return clean_num
        
    

async def scrape_sofmap(url: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url=url, timeout=60000)
        # await auto_scroll(page=page)

        item_containers = await page.locator("div.mainbox").all()
        results = []
        scraped_at = datetime.now(JST).isoformat()

        for item in item_containers:
            try:
                namepart = await item.locator("p.product_name").inner_text()
                brand = await item.locator("span.brand").inner_text()
                name = namepart + brand
                price_raw = await item.locator("span.price strong").inner_text()                
                price_text = price_raw.replace("¥", "").replace(",", "").replace("(税込)", "").strip()
                
                link = await item.locator("a.product_name").first.get_attribute("href")
                product_id = link.split("sku=")[-1]
                

                results.append({
                    "itemCode": product_id,
                    "itemName": name.strip(),
                    "itemPrice": int(price_text.replace(",", "")),
                    "scraped_at": scraped_at,
                    "search_query": "-",
                    "source": "sofmap",
                    "is_active": True,
                })
            except Exception:
                continue  # skip malformed items

        await browser.close()
        return results


def run_pckoubou_scraper() -> list[dict]:
    """Sync entry point — runs all configured search URLs."""
    all_results = []
    url = "https://www.sofmap.com/search_result.aspx?gid=001010110&used_rank=0009+0003+0002+0001+0006+0004&product_type=USED&order_by=&dispcnt=100"

    listingnum = asyncio.run(findmaxlisting(url = url))
    print(type(listingnum))
    
    pages = listingnum / 100 + 1
    print(f"Num of listings {listingnum}, pages : {pages}")
    for i in range(0, int(pages)):
        if i > 0:
            print("[sofmap] Waiting 10s before next URL...")
            time.sleep(10)
        
        results = asyncio.run(scrape_sofmap(url))
        print(f"[sofmap] {len(results)} items")
        print(results)
        all_results.extend(results)
    return all_results

run_pckoubou_scraper()