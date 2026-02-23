import asyncio
import time
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

SEARCH_URLS = {
    "used_lenovo_note": "https://www.pc-koubou.jp/pc/used_note_lenovo.php?pre=cmm_lup",
    "used_dell_note":   "https://www.pc-koubou.jp/pc/used_note_dell.php?pre=cmm_lup",
}


async def auto_scroll(page):
    previous_height = await page.evaluate("document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break
        previous_height = new_height


async def scrape_pckoubou(search_key: str, url: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url=url, timeout=60000)
        await auto_scroll(page=page)

        item_containers = await page.locator("div.info-area").all()
        results = []
        scraped_at = datetime.now(JST).isoformat()

        for item in item_containers:
            try:
                name = await item.locator("p.name").inner_text()
                price_text = await item.locator(".price--num").inner_text()
                product_id = await item.locator("span.link--add--clip").get_attribute("data-clip")
                results.append({
                    "itemCode": product_id,
                    "itemName": name.strip(),
                    "itemPrice": int(price_text.replace(",", "")),
                    "scraped_at": scraped_at,
                    "search_query": search_key,
                    "source": "pckoubou",
                    "is_active": True,
                })
            except Exception:
                continue  # skip malformed items

        await browser.close()
        return results


def run_pckoubou_scraper() -> list[dict]:
    """Sync entry point — runs all configured search URLs."""
    all_results = []
    for i, (key, url) in enumerate(SEARCH_URLS.items()):
        if i > 0:
            print("[pckoubou] Waiting 10s before next URL...")
            time.sleep(10)
        results = asyncio.run(scrape_pckoubou(key, url))
        print(f"[pckoubou] {key}: {len(results)} items")
        all_results.extend(results)
    return all_results
