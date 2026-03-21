import asyncio
import time
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))

SAMPLE_HTML = """
<ul>
<li>
<div class="info-area"><a class="" href="/products/detail.php?product_id=1217599"><p class="name">Lenovo  〔中古〕IdeaPad Slim3 14IRU9 インテル® Core™ 5 プロセッサー  120U/DDR5 16GB/512GB SSD/CPU内蔵/Windows 11 Home(中古保証3ヶ月間)</p><div class="multi-area"><div class="multi-area-1 item_title_bottom"><div class="item-comment">中古保証3ヶ月間</div><div class="spec">Windows 11 Home</div></div><div class="multi-area-2"><div class="label"><i><span>超還元 対象</span></i><i><span>中古延長保証可能</span></i></div><p class="btn-clip"><span class="link--add--clip" data-clip="1217599">この商品をお気に入り登録</span></p><div class="pirce-area"><div class="table"><div class="table-cell"><dl class="price__normal"><dt><span class="price--title"> </span></dt><dd><p class="price--notax"><span class="price--num">122,800</span><span class="price--safix">円</span></p></dd></dl></div></div></div></div></div></a></div>
</li>
<li>
<div class="info-area"><a class="" href="/products/detail.php?product_id=1216742"><p class="name">Lenovo  〔中古〕ThinkPad T490 インテル® Core™ i5 プロセッサー 8265U/DDR4 8GB/512GB SSD/GeForce MX250 (Laptop)/Windows 11 Home(MAR)(中古保証3ヶ月間)</p><div class="multi-area"><div class="multi-area-1 item_title_bottom"><div class="item-comment">中古保証3ヶ月間</div><div class="spec">Windows 11 Home</div></div><div class="multi-area-2"><div class="label"><i><span>超還元 対象</span></i><i><span>Office搭載可能</span></i><i><span>中古延長保証可能</span></i></div><p class="btn-clip"><span class="link--add--clip" data-clip="1216742">この商品をお気に入り登録</span></p><div class="pirce-area"><div class="table"><div class="table-cell"><dl class="price__normal"><dt><span class="price--title"> </span></dt><dd><p class="price--notax"><span class="price--num">46,981</span><span class="price--safix">円</span></p></dd></dl></div></div></div></div></div></a></div>
</li>
<li>
<div class="info-area"><a class="" href="/products/detail.php?product_id=1216725"><p class="name">Lenovo  〔中古〕ideapad Slim 5 Light 14ABR8 Ryzen 5 7530U/DDR4 16GB/512GB SSD/CPU内蔵/Windows 11 Home(中古保証3ヶ月間)</p><div class="multi-area"><div class="multi-area-1 item_title_bottom"><div class="item-comment">中古保証3ヶ月間</div><div class="spec">Windows 11 Home</div></div><div class="multi-area-2"><div class="label"><i><span>超還元 対象</span></i><i><span>中古延長保証可能</span></i></div><p class="btn-clip"><span class="link--add--clip" data-clip="1216725">この商品をお気に入り登録</span></p><div class="pirce-area"><div class="table"><div class="table-cell"><dl class="price__normal"><dt><span class="price--title"> </span></dt><dd><p class="price--notax"><span class="price--num">79,981</span><span class="price--safix">円</span></p></dd></dl></div></div></div></div></div></a></div>
</li>
<li>
<div class="info-area"><a class="" href="/products/detail.php?product_id=1216734"><p class="name">Lenovo  〔中古〕T495/1867 Ryzen 5 PRO 3500U 2.1GHz/8GB/256GB SSD/Radeon Vega8 Graphics/Windows 11 Pro(MAR)(中古保証3ヶ月間)</p><div class="multi-area"><div class="multi-area-1 item_title_bottom"><div class="item-comment">中古保証3ヶ月間</div><div class="spec">Windows 11 Pro</div></div><div class="multi-area-2"><div class="label"><i><span>超還元 対象</span></i><i><span>Office搭載可能</span></i><i><span>中古延長保証可能</span></i></div><p class="btn-clip"><span class="link--add--clip" data-clip="1216734">この商品をお気に入り登録</span></p><div class="pirce-area"><div class="table"><div class="table-cell"><dl class="price__normal"><dt><span class="price--title"> </span></dt><dd><p class="price--notax"><span class="price--num">39,980</span><span class="price--safix">円</span></p></dd></dl></div></div></div></div></div></a></div>
</li>
</ul>
"""

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
