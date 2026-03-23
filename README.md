# Rakuten Used Computer Finder

Price-comparison tool for used/refurbished laptops across Japanese marketplaces. Scrapes listings, stores them in Supabase, and provides a Streamlit dashboard with market price analysis per shop and model.

## Supported Marketplaces

| Source | Scraper | Method |
|---|---|---|
| Rakuten Ichiba | `rakuten_api.py` | Official API |
| PC Koubou | `pckoboscrape.py` | Web scraping |
| Sofmap (new) | `sofmapscrape.py` | Web scraping |
| Sofmap (used) | `sofmapscrape_used.py` | Web scraping (Playwright) |
| PC Wrap | `pcwrapscrape.py` | Web scraping |
| Qualit | `qualitscrape.py` | Web scraping (Playwright) |
| PC Baru | `pcbaruscrape.py` | Web scraping |
| Kakaku.com | `kakakucom_scrape.py` | Web scraping |

## Tech Stack

- **Python 3.12+** managed by [uv](https://docs.astral.sh/uv/)
- **Polars** for all dataframe operations
- **Supabase** (PostgreSQL) for storage
- **Streamlit** for the dashboard
- **Playwright** for JS-rendered pages
- **LightGBM / scikit-learn** for ML pricing models (WIP)

## Setup

```bash
# Install dependencies
uv sync

# Install Playwright browsers (needed for some scrapers)
uv run playwright install chromium

# Configure environment — create .env with:
#   SUPABASE_URL=https://xxx.supabase.co
#   SUPABASE_KEY=xxx
#   RAKUTEN_APP_ID=xxx
```

## Usage

```bash
# Run full scraper pipeline (all sources)
uv run python scraper.py

# Launch the dashboard
uv run streamlit run src/Marketprice_per_shop.py

# Run tests
uv run pytest tests/ -x --tb=short

# Lint & format
uv run ruff check src/ && uv run ruff format src/
```

## How It Works

1. **Scrape** — Each scraper fetches listings and returns `list[dict]` with fields like `item_name`, `price`, `shop_name`, `item_url`, etc.
2. **Extract specs** — CPU, RAM, storage, OS, and other specs are parsed from listing titles via string splitting and pattern matching (`extract_specs_1.py`).
3. **Upsert to Supabase** — `scraper.py` deduplicates by `item_code`, upserts into the `products` table, and appends to `price_history` for tracking price changes over time.
4. **Dashboard** — `Marketprice_per_shop.py` provides interactive filtering by model, shop, and specs, with price trend charts.

## Project Structure

```
├── scraper.py                 # Main pipeline — runs all scrapers, upserts to Supabase
├── src/
│   ├── rakuten_api.py         # Rakuten Ichiba API scraper
│   ├── pckoboscrape.py        # PC Koubou scraper
│   ├── sofmapscrape.py        # Sofmap scraper (new items)
│   ├── sofmapscrape_used.py   # Sofmap scraper (used items, Playwright)
│   ├── pcwrapscrape.py        # PC Wrap scraper
│   ├── qualitscrape.py        # Qualit scraper
│   ├── pcbaruscrape.py        # PC Baru scraper
│   ├── kakakucom_scrape.py    # Kakaku.com scraper
│   ├── extract_specs_1.py     # Spec extraction from listing titles
│   ├── Marketprice_per_shop.py # Streamlit dashboard
│   └── dashboard/             # Dashboard components
├── tests/                     # pytest test suite
├── data/                      # Raw/processed data, lookup tables
├── models/                    # Saved ML model artifacts
├── SCRAPER_GUIDE.md           # Guide for writing new scrapers
├── CLAUDE.md                  # AI assistant project instructions
└── pyproject.toml             # uv project config & dependencies
```

## Adding a New Scraper

See [SCRAPER_GUIDE.md](SCRAPER_GUIDE.md) for detailed instructions. In short:

1. Fetch sample HTML first for offline development
2. Create `src/newsitescrape.py` with a `run_newsite_scraper()` function returning `list[dict]`
3. Prefer simple string splitting over regex for spec parsing
4. Add the scraper call to `scraper.py`
5. Add tests in `tests/`

## License

Private project — not licensed for redistribution.
