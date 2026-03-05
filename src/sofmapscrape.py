"""
This is a scraping service to scrape used computers off of sofmap.com
"""
import asyncio
import time
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

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
