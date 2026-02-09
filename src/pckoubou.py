# from .base import BaseScraper
from spec_extractor import SpecExtractor
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

class PCKoubouScraper(BaseScraper):
    """Scraper for PC KOBO (パソコン工房)"""
    
    BASE_URL = "https://www.pc-koubou.jp"
    
    def __init__(self):
        # PC KOBO often needs JS for dynamic filters or search hydration
        super().__init__(use_playwright=True)
        self.spec_extractor = SpecExtractor()
    
    def get_search_url(self, keyword: str, page: int) -> str:
        # PC KOBO uses 'q' for keyword. 
        # Example: user_data/search.php?q=keyword
        return f"{self.BASE_URL}/user_data/search.php?q={quote(keyword)}"
    
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
    
    def parse_listing(self, element) -> Optional[Dict]:
        """Parse single PC KOBO listing"""
        try:
            # Title is in p.name
            title_elem = element.select_one('p.name')
            # Price is in .price--num or .price--current
            price_elem = element.select_one('.price--num') or element.select_one('.price--current')
            # Link is the main anchor
            link_elem = element.select_one('a')
            # Image is in .left-pict img
            img_elem = element.select_one('.left-pict img') or element.select_one('img')
            
            if not all([title_elem, price_elem]):
                return None
            
            title = title_elem.text.strip()
            price_text = price_elem.text.strip()
            
            # Extract price (remove ¥, commas, tax info)
            # Price usually looks like "¥123,456 (税込)"
            price_match = re.search(r'¥?([\d,]+)', price_text)
            if not price_match:
                return None
            price = int(price_match.group(1).replace(',', ''))
            
            # Extract URL
            url = link_elem['href'] if link_elem else None
            if url and not url.startswith('http'):
                url = self.BASE_URL + url
            
            # Extract image
            image_url = img_elem['src'] if img_elem else None
            if image_url and not image_url.startswith('http'):
                image_url = self.BASE_URL + image_url
            
            # Extract specs from title
            specs = self.spec_extractor.extract(title)
            
            return {
                'site': 'pckoubou',
                'title': title,
                'price': price,
                'url': url,
                'image_url': image_url,
                **specs
            }
            
        except Exception as e:
            return None