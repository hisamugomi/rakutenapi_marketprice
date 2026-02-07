import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional
import redis
from fastapi import BackgroundTasks
from ..scrapers.mercari import MercariScraper
from ..scrapers.pckoubou import PCKoubouScraper
from ..scrapers.rakuten import RakutenScraper
from ..models.database import get_db_context
from ..models.listing import Listing
from ..config import settings
import logging

logger = logging.getLogger(__name__)

# Helper to create redis client
def get_redis():
    return redis.from_url(settings.REDIS_URL, decode_responses=True)

# registry of available scrapers
# TO ADD A NEW SITE:
# 1. Create a new scraper class in scrapers/ folder
# 2. Import it here
# 3. Add it to this dictionary with a unique key
SCRAPERS = {
    'mercari': MercariScraper,
    'pckoubou': PCKoubouScraper,
    'rakuten': RakutenScraper,
}

class ScraperService:
    """Orchestrates scraping jobs"""
    
    @staticmethod
    def start_scraping(
        sites: List[str],
        keyword: str,
        max_pages: int,
        background_tasks: BackgroundTasks
    ) -> str:
        """Start a new scraping job"""
        
        job_id = str(uuid.uuid4())
        redis_client = get_redis()
        
        # Store job info in Redis
        job_data = {
            'id': job_id,
            'sites': sites,
            'keyword': keyword,
            'max_pages': max_pages,
            'status': 'pending',
            'progress': 0,
            'total': 0,
            'items_scraped': 0,
            'items_new': 0,
            'started_at': datetime.utcnow().isoformat(),
            'completed_at': None,
            'error': None
        }
        
        redis_client.setex(
            f"job:{job_id}",
            3600,  # Expire after 1 hour
            json.dumps(job_data)
        )
        
        # Run scraping in background
        background_tasks.add_task(
            ScraperService._run_scraping_job,
            job_id,
            sites,
            keyword,
            max_pages
        )
        
        return job_id
    
    @staticmethod
    def get_job_status(job_id: str) -> Dict:
        """Get status of scraping job"""
        redis_client = get_redis()
        job_data = redis_client.get(f"job:{job_id}")
        
        if not job_data:
            return {'error': 'Job not found'}
        
        return json.loads(job_data)
    
    @staticmethod
    def _update_job_status(job_id: str, updates: Dict):
        """Update job status in Redis"""
        redis_client = get_redis()
        job_data = redis_client.get(f"job:{job_id}")
        if job_data:
            data = json.loads(job_data)
            data.update(updates)
            redis_client.setex(f"job:{job_id}", 3600, json.dumps(data))
    
    @staticmethod
    async def _run_scraping_job(
        job_id: str,
        sites: List[str],
        keyword: str,
        max_pages: int
    ):
        """Execute scraping job"""
        
        try:
            ScraperService._update_job_status(job_id, {'status': 'running'})
            
            total_items = 0
            new_items = 0
            
            for site in sites:
                if site not in SCRAPERS:
                    continue
                
                scraper_class = SCRAPERS[site]
                scraper = scraper_class()
                
                # Scrape
                try:
                    results = scraper.scrape(keyword, max_pages)
                except Exception as e:
                    logger.error(f"Scraping failed for site {site}: {e}")
                    continue
                
                if not results:
                    continue

                # Save to database
                async with get_db_context() as db:
                     for result in results:
                        # Check if listing already exists (by URL)
                        # Note: Simple check here. In prod, careful with heavy queries.
                        from sqlalchemy import select
                        stmt = select(Listing).where(Listing.url == result.get('url'))
                        result_proxy = await db.execute(stmt)
                        existing = result_proxy.scalar_one_or_none()
                        
                        if not existing:
                            listing = Listing(**result)
                            db.add(listing)
                            new_items += 1
                        
                        total_items += 1
                     await db.commit()
                
                # Update progress
                ScraperService._update_job_status(job_id, {
                    'items_scraped': total_items,
                    'items_new': new_items
                })
            
            # Mark as completed
            ScraperService._update_job_status(job_id, {
                'status': 'completed',
                'completed_at': datetime.utcnow().isoformat(),
                'items_scraped': total_items,
                'items_new': new_items
            })
            
        except Exception as e:
            logger.error(f"Job failed: {e}")
            ScraperService._update_job_status(job_id, {
                'status': 'failed',
                'error': str(e),
                'completed_at': datetime.utcnow().isoformat()
            })
