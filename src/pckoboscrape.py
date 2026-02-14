import requests
from bs4 import BeautifulSoup
import pandas as pd
import polars as pl
import streamlit as st
import time
from typing import Optional
from urllib.parse import quote
import logger

class KoboScraperService:
    def __init__(self):
        # PC Kobo search URL
        super().__init__(use_playwright=True)
        self.spec_extractor = SpecExtractor()
        self.base_url = "https://www.pc-koubou.jp/products/search.php"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    def get_search_url(self, keyword : str, page:int) -> str:
        return f"{self.base_url}/user_data/search.php?q={quote(keyword)}"


    def _parse_page(self, soup: BeautifulSoup) -> List[Dict]:
        """Parse PC KOBO search results page"""
        listings = []
        
        # Identified container from browser inspection
        items = soup.select('.itemlist--1')
        
        for item in items:
            try:
                listing = self.parse_listing(item)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.error(f"Failed to parse listing: {e}")
                continue
        
        return listings

    # def _parse_page(self, html_content: str) -> pl.DataFrame:
    #     """
    #     Mimics your process_rakuten_json logic but for HTML.
    #     Extracts product details into a flat DataFrame.
    #     """
    #     soup = BeautifulSoup(html_content, "html.parser")
    #     items_list = []
        
    #     # PC Kobo listing containers
    #     items = soup.select(".product_list__item")
        
    #     for item in items:
    #         try:
    #             name = item.select_one(".product_list__name").get_text(strip=True)
    #             price_text = item.select_one(".product_list__price").get_text(strip=True)
    #             # Clean price: remove '¥' and ',' to keep it numeric
    #             price = price_text.replace("¥", "").replace(",", "").replace("（税込）", "").strip()
                
    #             link_tag = item.select_one("a")
    #             url = "https://www.pc-koubou.jp" + link_tag["href"] if link_tag else ""
                
    #             # PC Kobo puts basic specs in a specific div
    #             caption = item.select_one(".product_list__spec").get_text(strip=True) if item.select_one(".product_list__spec") else ""

    #             items_list.append({
    #                 "itemName": name,
    #                 "itemPrice": int(price) if price.isdigit() else price,
    #                 "itemUrl": url,
    #                 "itemCaption": caption,
    #                 "shopName": "PC Kobo (Used)",
    #                 "combined": f"{name} {caption}" # Ready for your AI extraction
    #             })
    #         except Exception:
    #             continue
                
    #     return pl.DataFrame(items_list)


    def parse_listing(self, element) -> Optional[dict]:
        try:
            title_elem = element.select_one("p.name")
            price_elem = element.select_one(".price--num") or element.select_one(".price--current")
            link_elem = element.select_one("a") 
            img_elem = element.select_one(".left-pict img") or element.select_one("img")

            if not all([title_elem, price_elem]):
                return None
            
            title = title_elem.text.strip()
            price = price_elem.text.strip()

        


        except

    def fetch_items(self, keyword: str, total_pages: int = 5):
        """
        The main loop, similar to your fetch_rakuten_items function.
        """
        all_dfs = []
        
        # Progress bar for Streamlit UI
        # progress_bar = st.progress(0)
        
        for page in range(1, total_pages + 1):
            params = {
                "keyword": keyword,
                "used_only": 1,      # Focus on used hardware
                "page": page,
            }

            try:
                response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
                response.raise_for_status()
                
                page_df = self._parse_page(response.text)

                if not page_df.is_empty():
                    all_dfs.append(page_df)
                    print(f"✅ Scraped PC Kobo page {page}: {len(page_df)} items found.")
                else:
                    print(f"🏁 No more items found on page {page}. Stopping.")
                    break

                # Update progress
                # progress_bar.progress(page / total_pages)
                
                # Respectful delay to avoid getting blocked
                time.sleep(2)

            except Exception as e:
                raise(f"Error scraping PC Kobo: {e}")
                # break


        if all_dfs:
            final_df = pl.concat(all_dfs, ignore_index=True)
            return final_df
        
        return pl.DataFrame()

# --- Streamlit Usage Example ---
scraper = KoboScraperService()
df = scraper.fetch_items("L390", total_pages=3)
print(df)