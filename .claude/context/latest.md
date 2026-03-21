# Context Snapshot
**Saved:** 2026-03-09
**Phase:** Scraper development — all scrapers integrated, dedup bug fixed
**Branch:** main

## What Was Accomplished
- Added 10 integration tests to `tests/test_scrapers/test_kakaku_scraper.py` — 35 total, all passing
- Created `src/pcwrapscrape.py`: moved from root, refactored with separated pure parser (`parse_pcwrap_listings` + BeautifulSoup), aligned fields to `_PRODUCT_COLS` (`memory`, `ssd`, `hdd`, `display_size`, `shopName`, `model`)
- Created `tests/test_scrapers/test_pcwrap_scraper.py` — 37 tests, all passing including live scrape
- Wired `run_pcwrap_scraper` and `run_kakaku_scraper` into `scraper.py`
- Added `beautifulsoup4` to `.github/workflows/scraper.yaml`
- Created `SCRAPER_GUIDE.md` — authoring manual for new scrapers
- Fixed `ON CONFLICT DO UPDATE command cannot affect row a second time` (error code 21000):
  - Root cause: same `itemCode` appearing multiple times in one batch (e.g. Kakaku returns same product under multiple search queries; Sofmap uses JAN barcodes as `itemCode` shared by multiple listings)
  - Fix: added `.unique(subset=["item_code"], keep="first")` in `_upsert_batch` before the upsert call
  - Committed as `781063a`, pushed to `origin/main`
- All committed and pushed (latest: `781063a`)

## Current State
- **Working on:** Nothing — session complete
- **Blocked by:** None
- **Files modified this session:**
  - `scraper.py` — pcwrap/kakaku integrated, dedup fix added (committed)
  - `src/pcwrapscrape.py` — new (committed)
  - `src/kakakucom_scrape.py` — new (committed)
  - `tests/test_scrapers/test_pcwrap_scraper.py` — new (committed)
  - `tests/test_scrapers/test_kakaku_scraper.py` — new (committed)
  - `.github/workflows/scraper.yaml` — beautifulsoup4 added (committed)
  - `SCRAPER_GUIDE.md` — new (committed)
- **Tests status:** 35/35 kakaku, 37/37 pcwrap — all passing
- **GitHub Actions:** Next run will have the dedup fix

## Key Decisions Made
- Dedup is done in `_upsert_batch` on `["item_code"]` — covers all scrapers universally
- Price history uses `extracted` (pre-dedup) — all price observations still recorded even for duplicate-code items
- Sofmap JAN codes (`new_jan=` URLs) are intentionally kept as `itemCode`; the dedup consolidates them per run
- Kakaku maps: `ram→memory`, `storage→ssd`, `screen→display_size` (strips "インチ"), `search_query→model`
- PCwrap fields pre-aligned in scraper — no `with_columns` needed in `scraper.py`
- Streamlit Cloud reads `requirements.txt` from repo root (separate from `pyproject.toml`)

## Next Steps (Priority Order)
1. Verify next GitHub Actions run completes without the 21000 error
2. Delete old `pcwrapscrape.py` from repo root (replaced by `src/pcwrapscrape.py`)
3. Address `tests/test_features/test_model_extractor.py` — imports `src.features.model_extractor` which doesn't exist; will crash pytest with `-x`
4. Consider updating `requirements.txt` for Streamlit Cloud dashboard deps
5. Begin ML pipeline phase (LightGBM price model, survival model)

## Open Questions
- Did the GitHub Actions workflow pass cleanly with the dedup fix?
- Should `rank` (condition grade from kakaku) be added to the DB schema?
- `src/sofmapscrape_copy.py` is untracked — probably safe to delete

## Important Notes
- `scraper.py` pipeline order: Rakuten → PCKoubou → PCwrap → Kakaku → Sofmap
- `_upsert_batch` rename map: `itemCode→item_code`, `itemName→item_name`, `itemUrl→item_url`, `shopName→shop_name`
- `_PRODUCT_COLS`: `item_code, source, item_name, item_url, shop_name, search_query, brand, model, cpu, cpu_gen, memory, ssd, hdd, os, display_size, weight, bluetooth, webcam, usb_ports, is_active, last_seen_at`
- `price_history` columns: `product_id`, `item_code`, `source`, `price`, `scraped_at`, `search_query`
- `price_history` column is `scraped_at` (NOT `observed_at`)
- Dedup happens on `item_code` only (all rows in a batch share the same `source`)
- Never touch `.env` or `secrets.toml`
- Always use Polars, never pandas
- `bs4` installed, `selectolax` NOT installed

## File Map
```
src/kakakucom_scrape.py              — kakaku scraper + parser (committed)
src/pcwrapscrape.py                  — pcwrap scraper + parser (committed)
pcwrapscrape.py                      — OLD root file, not yet deleted
tests/test_scrapers/test_kakaku_scraper.py   — 35 tests (committed)
tests/test_scrapers/test_pcwrap_scraper.py   — 37 tests (committed)
tests/test_scrapers/test_scraper.py          — 20 tests rakuten/pckoubou/sofmap (committed)
scraper.py                           — main pipeline, all 5 scrapers + dedup fix (committed)
.github/workflows/scraper.yaml       — beautifulsoup4 added (committed)
SCRAPER_GUIDE.md                     — scraper authoring manual (committed)
```

## Git Log (recent)
```
781063a fix: deduplicate item_code before upsert to avoid ON CONFLICT row conflict
5299383 feat: add kakaku + pcwrap scrapers, integrate into pipeline  (note: may show as c4d59f2 depending on ref)
b0d2cc6 Add PCWrap laptop scraper
```
