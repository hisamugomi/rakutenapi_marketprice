import sys
import os
import logging
import json

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.scrapers.pckoubou import PCKoubouScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("Starting PC KOBO Debug Scraper...")
    
    scraper = PCKoubouScraper()
    keyword = "Dell XPS"
    
    print(f"Scraping keyword: {keyword}")
    
    try:
        results = scraper.scrape(keyword, max_pages=1)
        
        print(f"\nFound {len(results)} items.")
        
        if results:
            print("\nFirst 3 items found:")
            print(json.dumps(results[:3], indent=2, ensure_ascii=False))
        else:
            print("\nNo items found.")
            
    except Exception as e:
        print(f"Error during scraping: {e}")

if __name__ == "__main__":
    main()